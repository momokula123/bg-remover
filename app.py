import os
import uuid
import io
import base64
import time
from flask import Flask, render_template, request, jsonify, send_file

os.environ['U2NET_HOME'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')

from rembg import remove, new_session
from PIL import Image

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, 'inputs')
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs')
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

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


def get_session(model_name):
    if model_name not in _session_cache:
        t0 = time.time()
        print(f'  加载模型: {model_name} ...')
        _session_cache[model_name] = new_session(model_name)
        print(f'  模型 {model_name} 加载完成 ({time.time()-t0:.1f}s)')
    return _session_cache[model_name]


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api')
def api_docs():
    return render_template('api.html')


@app.route('/api/models')
def list_models():
    models = []
    for key, info in MODEL_INFO.items():
        model_path = os.path.join(BASE_DIR, 'models', info['file'])
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


@app.route('/api/remove', methods=['POST'])
def remove_bg():
    if 'image' not in request.files:
        return jsonify({'error': '请上传图片文件 (field: image)'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400

    model_name = request.form.get('model', 'birefnet-massive')
    if model_name not in MODEL_INFO:
        return jsonify({'error': f'不支持的模型: {model_name}, 可选: {list(MODEL_INFO.keys())}'}), 400

    allowed_ext = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({'error': f'不支持的格式: {ext}'}), 400

    try:
        t0 = time.time()
        input_data = file.read()
        session = get_session(model_name)
        output_data = remove(input_data, session=session)

        result_img = Image.open(io.BytesIO(output_data))
        if result_img.mode != 'RGBA':
            result_img = result_img.convert('RGBA')

        uid = uuid.uuid4().hex[:8]
        output_filename = f"{uid}_nobg.png"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        result_img.save(output_path, 'PNG')

        buffered = io.BytesIO()
        result_img.save(buffered, format='PNG')
        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        elapsed = round(time.time() - t0, 2)

        return jsonify({
            'success': True,
            'image': f'data:image/png;base64,{img_b64}',
            'filename': output_filename,
            'download_url': f'/api/download/{output_filename}',
            'model': model_name,
            'model_name': MODEL_INFO[model_name]['name'],
            'elapsed_seconds': elapsed,
            'original_size': list(result_img.size),
        })

    except Exception as e:
        return jsonify({'error': f'处理失败: {str(e)}'}), 500


@app.route('/api/remove/file', methods=['POST'])
def remove_bg_file():
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
        input_data = file.read()
        session = get_session(model_name)
        output_data = remove(input_data, session=session)

        result_img = Image.open(io.BytesIO(output_data))
        if result_img.mode != 'RGBA':
            result_img = result_img.convert('RGBA')

        uid = uuid.uuid4().hex[:8]
        output_filename = f"{uid}_nobg.png"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        result_img.save(output_path, 'PNG')

        return send_file(output_path, mimetype='image/png', as_attachment=False)

    except Exception as e:
        return jsonify({'error': f'处理失败: {str(e)}'}), 500


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
        'models': {k: os.path.exists(os.path.join(BASE_DIR, 'models', v['file'])) for k, v in MODEL_INFO.items()},
        'loaded_sessions': list(_session_cache.keys()),
    })


if __name__ == '__main__':
    print()
    print('=' * 55)
    print('  AI 图片背景移除工具 已启动')
    print('  Web UI:   http://127.0.0.1:5000')
    print('  API 文档: http://127.0.0.1:5000/api')
    print('=' * 55)
    print()
    app.run(debug=False, host='0.0.0.0', port=5000)
