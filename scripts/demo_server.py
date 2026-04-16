import json
import os
import sys
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# 添加父目录到Python路径，以便导入codes和run_match模块
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from codes.trial_matcher import build_patient_input, load_trials, rank_trials
from run_match import render_html, save_html

ROOT_DIR = PROJECT_ROOT
TRIAL_JSON_PATH = ROOT_DIR / 'original_data' / 'clinical_trials' / 'trials_structured.json'
OUTPUT_DIR = ROOT_DIR / 'output_patients'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_biomarkers(value):
    if not value:
        return []
    return [item.strip() for item in value.replace('，', ',').split(',') if item.strip()]


class DemoHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('', '/', '/index.html'):
            self.path = '/web/demo_input.html'
        elif self.path == '/demo_input.html':
            self.path = '/web/demo_input.html'
        return super().do_GET()

    def do_POST(self):
        if self.path != '/run_match':
            return super().do_POST()

        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        form = urllib.parse.parse_qs(body)

        diagnosis = form.get('diagnosis', [''])[0].strip()
        cancer_stage = form.get('cancer_stage', [''])[0].strip()
        age = parse_int(form.get('age', [''])[0])
        gender = form.get('gender', [''])[0].strip()
        ecog = form.get('ecog', [''])[0].strip() or None
        treatment_lines = parse_int(form.get('treatment_lines', [''])[0])
        province = form.get('province', [''])[0].strip()
        city = form.get('city', [''])[0].strip()
        biomarkers = parse_biomarkers(form.get('biomarkers', [''])[0])

        location = f"{province} {city}".strip()

        patient = build_patient_input(
            diagnosis=diagnosis,
            cancer_stage=cancer_stage,
            age=age,
            gender=gender,
            ecog=None if ecog == '不限' else parse_int(ecog) if ecog else None,
            treatment_lines=treatment_lines,
            location=location,
            biomarkers=biomarkers,
        )

        trials = load_trials(str(TRIAL_JSON_PATH))
        matches = rank_trials(patient, trials, top_n=20)

        output_json_path = OUTPUT_DIR / 'patient_trial_matches.json'
        with output_json_path.open('w', encoding='utf-8') as f:
            json.dump({'patient': patient, 'matches': matches}, f, ensure_ascii=False, indent=2)

        html_text = render_html(patient, matches)
        save_html(OUTPUT_DIR, html_text)

        self.send_response(303)
        self.send_header('Location', '/output_patients/patient_trial_matches.html')
        self.end_headers()


if __name__ == '__main__':
    os.chdir(str(ROOT_DIR))

    host = '127.0.0.1'
    port = 8000
    server = HTTPServer(
        (host, port),
        lambda *args, **kwargs: DemoHandler(*args, directory=str(ROOT_DIR), **kwargs)
    )
    print(f'Demo server running at http://{host}:{port}/')
    print('打开浏览器访问输入页面，填写后提交即可查看匹配结果。')
    server.serve_forever()
