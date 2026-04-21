"""
快速运行匹配系统：输入结构化患者信息，输出候选临床试验，并生成静态HTML结果页面。
"""
import html
import json
from pathlib import Path

from codes.trial_matcher import build_patient_input, load_trials, rank_trials


def render_html(
    patient: dict, matches: list, match_mode: str = "strict", data_quality: dict | None = None
) -> str:
    patient_rows = []
    for key, label in [
        ('diagnosis', '诊断'),
        ('cancer_stage', '分期'),
        ('age', '年龄'),
        ('gender', '性别'),
        ('ecog', 'ECOG'),
        ('treatment_lines', '治疗线数'),
        ('location', '地理位置'),
        ('biomarkers', '生物标志物'),
    ]:
        value = patient.get(key)
        if isinstance(value, list):
            value = '、'.join(value)
        patient_rows.append(f'<tr><th>{html.escape(label)}</th><td>{html.escape(str(value)) if value is not None else "-"}</td></tr>')

    dq = data_quality or {}
    quality_rows = [
        ("lab_rows_total", "化验条目总数"),
        ("lab_observations_total", "可计算化验项"),
        ("genomics_rows_total", "基因条目数"),
        ("meta_rows_total", "分流元数据条目"),
        ("unknown_status_rows", "无法判断状态条目"),
    ]
    quality_html = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(dq.get(key, '-')))}</td></tr>"
        for key, label in quality_rows
    )
    missing_core = dq.get("missing_core_fields") or []
    missing_core_text = "、".join(str(x) for x in missing_core) if missing_core else "无"

    match_items = []
    for idx, item in enumerate(matches, start=1):
        trial = item.get('trial', {})
        reasons = item.get('reasons', []) or []
        reasons_html = '<br>'.join(html.escape(r) for r in reasons) if reasons else '<span class="dim">无明显不符</span>'
        next_steps = item.get('next_steps', []) or []
        next_steps_html = '<br>'.join(html.escape(str(s)) for s in next_steps) if next_steps else '<span class="dim">无</span>'
        checks = item.get('checks', []) or []
        checks_rows = []
        for check in checks:
            metric = str(check.get('metric_id') or '-')
            field_name = '入组' if check.get('field') == 'inclusion' else '排除'
            status = str(check.get('status') or 'unknown')
            patient_value = check.get('patient_value')
            threshold = check.get('threshold')
            operator = check.get('operator')
            evidence = str(check.get('evidence') or '')
            message = str(check.get('message') or '')
            status_text = {'pass': '通过', 'fail': '未通过', 'unknown': '待核对'}.get(status, status)
            patient_value_text = '-' if patient_value is None else str(patient_value)
            threshold_text = '-'
            if threshold is not None and operator:
                threshold_text = f"{operator}{threshold}"
            checks_rows.append(
                "<tr>"
                f"<td>{html.escape(field_name)}</td>"
                f"<td>{html.escape(metric)}</td>"
                f"<td>{html.escape(status_text)}</td>"
                f"<td>{html.escape(patient_value_text)}</td>"
                f"<td>{html.escape(threshold_text)}</td>"
                f"<td>{html.escape(message or evidence or '-')}</td>"
                "</tr>"
            )
        checks_table_html = (
            "<table>"
            "<tr><th>条款类型</th><th>指标</th><th>判定</th><th>患者值</th><th>阈值/规则</th><th>说明/证据</th></tr>"
            + "".join(checks_rows)
            + "</table>"
        ) if checks_rows else "<p class='dim'>当前试验未抽取到可计算的细则条款。</p>"
        
        # 高亮最近的地点
        nearest = item.get('nearest_location')
        province_str = str(trial.get('研究中心所在省份', '-'))
        city_str = str(trial.get('研究中心所在城市', '-'))
        
        if nearest:
            nearest_loc = nearest.get('location', '')
            if nearest['type'] == 'city':
                # 高亮city中最近的那个
                cities = [c.strip() for c in city_str.split(',')]
                city_str = '、'.join(
                    f'<span class="matched">{html.escape(c)}</span>' if c == nearest_loc else html.escape(c)
                    for c in cities
                )
            else:
                # 高亮province中最近的那个
                provinces = [p.strip() for p in province_str.split(',')]
                province_str = '、'.join(
                    f'<span class="matched">{html.escape(p)}</span>' if p == nearest_loc else html.escape(p)
                    for p in provinces
                )
        else:
            province_str = html.escape(province_str)
            city_str = html.escape(city_str)
        
        summary_location = province_str + ' ' + city_str
        patient_location = html.escape(str(patient.get('location') or '-'))
        matched_labels = item.get('matching_labels', [])
        labels = trial.get('labels', [])
        labels_html = '、'.join(
            f'<span class="matched">{html.escape(label)}</span>' if label in matched_labels else html.escape(label)
            for label in labels
        ) or '-'
        location_match_text = '<span class="matched">匹配</span>' if item.get('location_match') else '<span class="dim">未匹配</span>'
        geo_distance_text = f"{item.get('geo_distance'):.1f}" if isinstance(item.get('geo_distance'), (int, float)) else '-'
        match_items.append(f"""
        <div class="card">
          <button class="toggle-btn" onclick="toggleDetail('detail-{idx}')">
            <div class="summary-left">
              <div class="trial-title">{idx}. {html.escape(item.get('trial_name') or item.get('trial_id') or '未知试验')}</div>
              <div class="trial-meta">试验编码: {html.escape(str(item.get('trial_id')))} | 总分: {item.get('score', 0):.1f} | 地理排序: {item.get('geo_rank')} | 距离: {geo_distance_text} km</div>
              <div class="trial-meta location-meta">患者位置: {patient_location} → 研究中心: {summary_location}</div>
            </div>
          </button>
          <div id="detail-{idx}" class="detail">
            <div class="detail-block">
              <h3>符合信息</h3>
              <p><strong>患者诊断:</strong> {html.escape(str(patient.get('diagnosis') or '-'))}</p>
              <p><strong>试验疾病标签:</strong> {labels_html}</p>
              <p><strong>研究中心地点:</strong> {summary_location} {location_match_text}</p>
            </div>
            <div class="detail-block">
              <h3>匹配结果</h3>
              <p><strong>是否入选:</strong> {'✔ 入选' if item.get('eligible') else '✖ 未入选'}</p>
              <p><strong>疾病匹配:</strong> {'✔' if item.get('disease_match') else '✖'}</p>
              <p><strong>硬规则通过:</strong> 年龄 {'✔' if item.get('age_pass') else '✖'} / 性别 {'✔' if item.get('gender_pass') else '✖'} / ECOG {'✔' if item.get('ecog_pass') else '✖'} / 治疗线数 {'✔' if item.get('treatment_lines_pass') else '✖'} / 化验 {'✔' if item.get('lab_pass') else '✖'}</p>
              <p><strong>地理得分:</strong> {item.get('geo_rank')} | <strong>距离:</strong> {geo_distance_text} km</p>
              <p><strong>匹配理由 / 问题:</strong> {reasons_html}</p>
              <p><strong>建议补充:</strong> {next_steps_html}</p>
            </div>
            <div class="detail-block">
              <h3>试验条件细则对照（含患者指标）</h3>
              {checks_table_html}
            </div>
            <div class="detail-block">
              <h3>试验原始信息</h3>
              <table>
                <tr><th>疾病三级标签</th><td>{labels_html}</td></tr>
                <tr><th>入组条件</th><td><pre>{html.escape(str(trial.get('入组条件', '-')))}</pre></td></tr>
                <tr><th>排除条件</th><td><pre>{html.escape(str(trial.get('排除条件', '-')))}</pre></td></tr>
                <tr><th>研究中心省份</th><td class="{'matched' if nearest and nearest['type'] == 'province' else ''}">{html.escape(str(trial.get('研究中心所在省份', '-')))}</td></tr>
                <tr><th>研究中心城市</th><td class="{'matched' if nearest and nearest['type'] == 'city' else ''}">{html.escape(str(trial.get('研究中心所在城市', '-')))}</td></tr>
                <tr><th>研究医院</th><td>{html.escape(str(trial.get('研究医院', '-')))}</td></tr>
              </table>
            </div>
          </div>
        </div>
        """)

    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>患者临床试验匹配结果</title>
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 24px; background: #f4f7fb; color: #212121; }}
    h1 {{ margin-bottom: 8px; }}
    .panel {{ background: #fff; border-radius: 12px; box-shadow: 0 12px 40px rgba(20, 40, 80, 0.08); padding: 20px; margin-bottom: 24px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 12px; vertical-align: top; }}
    th {{ width: 130px; text-align: left; color: #444; }}
    pre {{ white-space: pre-wrap; word-break: break-word; margin: 0; font-family: inherit; font-size: 13px; background: #fafafa; padding: 12px; border-radius: 6px; border: 1px solid #eee; }}
    .card {{ margin-bottom: 14px; border-left: 4px solid #4f86ff; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 6px 20px rgba(0, 0, 0, 0.04); }}
    .toggle-btn {{ width: 100%; border: none; background: none; padding: 18px 20px; text-align: left; cursor: pointer; display: flex; justify-content: space-between; gap: 12px; align-items: center; }}
    .toggle-btn:hover {{ background: #f5f8ff; }}
    .summary-left {{ flex: 1; }}
    .trial-title {{ font-size: 16px; font-weight: 700; margin-bottom: 4px; }}
    .trial-meta {{ color: #666; font-size: 13px; }}
    .summary-right {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 6px 10px; font-size: 12px; font-weight: 700; color: #fff; }}
    .pass {{ background: #26a65b; }}
    .fail {{ background: #e74c3c; }}
    .detail {{ display: none; border-top: 1px solid #eceef3; background: #fcfdff; padding: 18px 20px; }}
    .detail-block {{ margin-bottom: 18px; }}
    .detail-block h3 {{ margin: 0 0 8px 0; font-size: 15px; }}
    .matched {{ background: #e6ffed; color: #1b6b28; border-radius: 4px; padding: 2px 6px; }}
    .dim {{ color: #777; }}
    .trial-meta.location-meta {{ margin-top: 6px; color: #555; font-size: 13px; }}
  </style>
</head>
<body>
  <div class="panel">
    <h1>患者匹配结果</h1>
    <p>匹配模式：<strong>{html.escape(match_mode)}</strong>。请点击每个试验展开详情。</p>
    <table>
      {''.join(patient_rows)}
    </table>
  </div>

  <div class="panel">
    <h2>输入数据质量</h2>
    <table>
      {quality_html}
      <tr><th>缺失核心字段</th><td>{html.escape(missing_core_text)}</td></tr>
    </table>
  </div>

  <div class="panel">
    <h2>候选试验列表（{len(matches)} 条）</h2>
    {''.join(match_items)}
  </div>

  <script>
    function toggleDetail(id) {{
      const el = document.getElementById(id);
      if (!el) return;
      el.style.display = el.style.display === 'block' ? 'none' : 'block';
    }}
  </script>
</body>
</html>
"""


def save_html(output_dir: Path, html_text: str) -> Path:
    output_path = output_dir / 'patient_trial_matches.html'
    output_path.write_text(html_text, encoding='utf-8')
    return output_path


def main():
    json_path = Path('original_data/clinical_trials/trials_structured.json')
    if not json_path.exists():
        raise FileNotFoundError(f'试验库文件不存在: {json_path}')

    trials = load_trials(str(json_path))

    # 这里填入患者的指定结构化信息，先不用OCR
    patient = build_patient_input(
        diagnosis='胆管癌',
        cancer_stage='IIIB',
        age=52,
        gender='女',
        ecog=1,
        treatment_lines=2,
        location='四川成都',
        biomarkers=['MSI-H', 'PD-L1']
    )

    matched = rank_trials(patient, trials, top_n=20)

    output_dir = Path('output_patients')
    output_dir.mkdir(parents=True, exist_ok=True)
    output_json_path = output_dir / 'patient_trial_matches.json'
    output_html_path = output_dir / 'patient_trial_matches.html'

    with output_json_path.open('w', encoding='utf-8') as f:
        json.dump({'patient': patient, 'matches': matched}, f, ensure_ascii=False, indent=2)

    html_text = render_html(patient, matched, match_mode="strict")
    save_html(output_dir, html_text)

    print('已生成候选试验结果：', output_json_path)
    print('已生成可视化页面：', output_html_path)
    print('\n前10条候选试验：')
    for idx, item in enumerate(matched[:10], start=1):
        geo_distance_text = f"{item.get('geo_distance'):.1f}" if isinstance(item.get('geo_distance'), (int, float)) else 'N/A'
        print(f"{idx}. {item['trial_id']} | score={item['score']:.1f} | geo_rank={item['geo_rank']} | geo_distance={geo_distance_text} | age_pass={item['age_pass']} | ecog_pass={item['ecog_pass']} | treatment_lines_pass={item['treatment_lines_pass']}")
        print(f"   trial_name: {item['trial_name']}")
        print(f"   reasons: {item['reasons']}")
        print()

    return matched


if __name__ == '__main__':
    main()
