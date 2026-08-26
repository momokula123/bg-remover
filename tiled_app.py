"""
分块抠图 (Tiled Background Removal) - 独立服务
复用 bg-remover 项目的 models 目录与 venv, 不修改原 app.py
端口: 5001 (原 app.py 用 5000, 互不干扰)
"""
import os
import io
import uuid
import time
import base64
import threading
import numpy as np
from flask import Flask, render_template, request, jsonify, send_file

# ============ 复用原项目的 models / outputs 目录 ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, 'models')
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs', 'tiled')
INPUT_DIR = os.path.join(BASE_DIR, 'inputs', 'tiled')
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(INPUT_DIR, exist_ok=True)

os.environ['U2NET_HOME'] = MODELS_DIR

from rembg import remove, new_session
from PIL import Image

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64MB, 大图友好

# ============ 模型清单 (与原项目一致) ============
MODEL_INFO = {
    'birefnet-massive': {
        'name': 'BiRefNet-Massive (最强)',
        'desc': '最大最强模型，训练数据最多，效果最佳，速度较慢',
        'quality': 5,
        'speed': 1,
        'file': 'birefnet-massive.onnx',
    },
    'bria-rmbg': {
        'name': 'BRIA-RMBG-2.0 (商业级)',
        'desc': '商业级背景移除模型，精度高速度快',
        'quality': 4,
        'speed': 3,
        'file': 'bria-rmbg.onnx',
    },
}

_session_cache = {}
_session_lock = threading.Lock()


def get_session(model_name):
    """懒加载并缓存 rembg session"""
    with _session_lock:
        if model_name not in _session_cache:
            t0 = time.time()
            print(f'  加载模型: {model_name} ...')
            _session_cache[model_name] = new_session(model_name)
            print(f'  模型 {model_name} 加载完成 ({time.time()-t0:.1f}s)')
        return _session_cache[model_name]


# ============ 分块抠图核心 ============
_jobs = {}            # job_id -> 任务状态
_jobs_lock = threading.Lock()


def _compute_tiles(W, H, tile_size, overlap):
    """计算分块起始坐标 (带重叠, 覆盖到边缘)"""
    step = max(1, tile_size - overlap)
    xs = list(range(0, max(1, W - tile_size + 1), step))
    ys = list(range(0, max(1, H - tile_size + 1), step))
    if not xs or xs[-1] + tile_size < W:
        xs.append(max(0, W - tile_size))
    if not ys or ys[-1] + tile_size < H:
        ys.append(max(0, H - tile_size))
    return sorted(set(xs)), sorted(set(ys))


def _tile_weight(th, tw, overlap):
    """余弦渐变权重窗, 重叠区域平滑融合, 避免拼接缝"""
    wx = np.ones(tw, dtype=np.float32)
    wy = np.ones(th, dtype=np.float32)
    ramp = min(overlap, tw // 2)
    if ramp > 1:
        ramp_arr = 0.5 - 0.5 * np.cos(np.pi * (np.arange(ramp) + 1) / ramp)
        wx[:ramp] = ramp_arr
        wx[-ramp:] = ramp_arr[::-1]
    ramp_y = min(overlap, th // 2)
    if ramp_y > 1:
        ramp_arr_y = 0.5 - 0.5 * np.cos(np.pi * (np.arange(ramp_y) + 1) / ramp_y)
        wy[:ramp_y] = ramp_arr_y
        wy[-ramp_y:] = ramp_arr_y[::-1]
    return np.outer(wy, wx)


def _run_tiled_job(job_id, input_path, model_name, tile_size, overlap):
    """后台线程: 逐块抠图 -> 加权融合 -> 合成透明 PNG"""
    try:
        with _jobs_lock:
            _jobs[job_id]['status'] = 'processing'

        t0 = time.time()
        img = Image.open(input_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        W, H = img.size
        img_np = np.array(img)

        session = get_session(model_name)
        xs, ys = _compute_tiles(W, H, tile_size, overlap)
        total = len(xs) * len(ys)

        mask_full = np.zeros((H, W), dtype=np.float32)
        weight_full = np.zeros((H, W), dtype=np.float32)
        done = 0

        for y0 in ys:
            for x0 in xs:
                x1 = min(x0 + tile_size, W)
                y1 = min(y0 + tile_size, H)
                tile = img.crop((x0, y0, x1, y1))

                buf = io.BytesIO()
                tile.save(buf, format='PNG')
                out_data = remove(buf.getvalue(), session=session)
                tile_out = Image.open(io.BytesIO(out_data))
                if tile_out.mode != 'RGBA':
                    tile_out = tile_out.convert('RGBA')
                tile_alpha = np.array(tile_out)[:, :, 3].astype(np.float32)
                th, tw = tile_alpha.shape
                w_tile = _tile_weight(th, tw, overlap)

                mask_full[y0:y1, x0:x1] += tile_alpha * w_tile
                weight_full[y0:y1, x0:x1] += w_tile
                done += 1
                with _jobs_lock:
                    _jobs[job_id]['done'] = done
                    _jobs[job_id]['progress'] = round(done / total * 100, 1)

        mask_full = np.where(weight_full > 0,
                             mask_full / np.maximum(weight_full, 1e-8), 0)
        mask_full = np.clip(mask_full, 0, 255).astype(np.uint8)
        rgba = np.dstack([img_np, mask_full])
        result = Image.fromarray(rgba, 'RGBA')

        out_name = f"{job_id}_tiled_nobg.png"
        out_path = os.path.join(OUTPUT_DIR, out_name)
        result.save(out_path, 'PNG')

        elapsed = round(time.time() - t0, 2)
        with _jobs_lock:
            _jobs[job_id]['status'] = 'done'
            _jobs[job_id]['result_path'] = out_path
            _jobs[job_id]['filename'] = out_name
            _jobs[job_id]['elapsed'] = elapsed
            _jobs[job_id]['size'] = list(result.size)
            _jobs[job_id]['tiles'] = total
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id]['status'] = 'error'
            _jobs[job_id]['error'] = str(e)


# ============ 路由 ============
@app.route('/')
def index():
    return render_template('tiled.html')


@app.route('/api/models')
def list_models():
    models = []
    for key, info in MODEL_INFO.items():
        model_path = os.path.join(MODELS_DIR, info['file'])
        models.append({
            'id': key,
            'name': info['name'],
            'desc': info['desc'],
            'quality': info['quality'],
            'speed': info['speed'],
            'downloaded': os.path.exists(model_path),
            'file_size': os.path.getsize(model_path) if os.path.exists(model_path) else 0,
        })
    return jsonify({'models': models, 'default': 'birefnet-massive'})


@app.route('/api/remove/tiled', methods=['POST'])
def remove_bg_tiled():
    if 'image' not in request.files:
        return jsonify({'error': '请上传图片文件 (field: image)'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400

    model_name = request.form.get('model', 'birefnet-massive')
    if model_name not in MODEL_INFO:
        return jsonify({'error': f'不支持的模型: {model_name}'}), 400

    allowed_ext = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({'error': f'不支持的格式: {ext}'}), 400

    try:
        tile_size = int(request.form.get('tile_size', 1024))
        overlap = int(request.form.get('overlap', 128))
    except ValueError:
        return jsonify({'error': 'tile_size/overlap 必须是整数'}), 400

    tile_size = max(256, min(tile_size, 4096))
    overlap = max(0, min(overlap, tile_size // 2))

    job_id = uuid.uuid4().hex[:8]
    input_path = os.path.join(INPUT_DIR, f"{job_id}_src{ext}")
    file.save(input_path)

    try:
        img = Image.open(input_path)
        W, H = img.size
    except Exception as e:
        return jsonify({'error': f'无法读取图片: {e}'}), 400

    xs, ys = _compute_tiles(W, H, tile_size, overlap)
    total_tiles = len(xs) * len(ys)

    with _jobs_lock:
        _jobs[job_id] = {
            'status': 'queued',
            'progress': 0,
            'total_tiles': total_tiles,
            'done': 0,
            'model': model_name,
            'tile_size': tile_size,
            'overlap': overlap,
            'input_size': [W, H],
            'error': None,
        }

    threading.Thread(
        target=_run_tiled_job,
        args=(job_id, input_path, model_name, tile_size, overlap),
        daemon=True
    ).start()

    return jsonify({
        'success': True,
        'job_id': job_id,
        'status': 'queued',
        'total_tiles': total_tiles,
        'input_size': [W, H],
    })


@app.route('/api/remove/tiled/status')
def tiled_status():
    job_id = request.args.get('job_id', '')
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({'error': '任务不存在'}), 404

    resp = {
        'status': job['status'],
        'progress': job['progress'],
        'done': job['done'],
        'total_tiles': job['total_tiles'],
    }
    if job['status'] == 'done':
        resp.update({
            'filename': job['filename'],
            'download_url': f'/api/download/{job["filename"]}',
            'elapsed': job['elapsed'],
            'size': job['size'],
            'tiles': job['tiles'],
        })
        with open(job['result_path'], 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')
        resp['image'] = f'data:image/png;base64,{img_b64}'
    elif job['status'] == 'error':
        resp['error'] = job['error']
    return jsonify(resp)


@app.route('/api/download/<filename>')
def download_file(filename):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        return jsonify({'error': '文件不存在'}), 404
    return send_file(path, as_attachment=True, download_name=filename, mimetype='image/png')


@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'tiled-bg-remover',
        'models': {k: os.path.exists(os.path.join(MODELS_DIR, v['file'])) for k, v in MODEL_INFO.items()},
        'loaded_sessions': list(_session_cache.keys()),
    })


if __name__ == '__main__':
    print()
    print('=' * 55)
    print('  分块抠图服务 已启动 (Tiled Background Removal)')
    print('  Web UI:   http://127.0.0.1:5001')
    print('  健康检查: http://127.0.0.1:5001/api/health')
    print('  模型目录:', MODELS_DIR)
    print('=' * 55)
    print()
    app.run(debug=True, host='0.0.0.0', port=5001, use_reloader=False)
