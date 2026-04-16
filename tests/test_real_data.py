from codes.trial_matcher import compute_geo_distance, find_nearest_location, geo_score

# 测试实际数据
print('=== 测试实际试验数据 ===')

# 试验编码: SCTB39G-X201 的沈阳中心
province = "河北省,上海市,湖南省,北京市,天津市,北京市,广西壮族自治区,湖北省,辽宁省,山东省"
city = "保定市,上海市,长沙市,北京市,天津市,北京市,南宁市,武汉市,沈阳市,潍坊市"

patient_loc = "辽宁沈阳"

dist = compute_geo_distance(patient_loc, province, city)
print(f'患者位置: {patient_loc}')
print(f'试验省份(前几个): {province[:50]}...')
print(f'试验城市(前几个): {city[:50]}...')
print(f'最短距离: {dist:.1f} km' if dist else '距离: 无')

nearest = find_nearest_location(patient_loc, province, city)
if nearest:
    print(f'最近地点: {nearest["location"]} ({nearest["type"]}) - {nearest["distance"]:.1f} km')

# 测试 geo_score
rank, distance = geo_score(patient_loc, province, city)
print(f'\ngeo_score 结果:')
print(f'  排序等级: {rank}')
print(f'  距离: {distance:.1f} km' if distance else '  距离: 无')
