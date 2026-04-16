from codes.trial_matcher import find_location_coord, compute_geo_distance, find_nearest_location

# 测试坐标查找
print('=== 坐标查找测试 ===')
print(f'沈阳: {find_location_coord("沈阳")}')
print(f'沈阳市: {find_location_coord("沈阳市")}')
print(f'辽宁: {find_location_coord("辽宁")}')
print(f'辽宁省: {find_location_coord("辽宁省")}')

# 测试距离计算
print('\n=== 距离计算测试（单点） ===')
dist = compute_geo_distance('辽宁沈阳', '辽宁省', '沈阳市')
print(f'患者:辽宁沈阳 -> 试验:辽宁省/沈阳市 -> 距离: {dist:.1f} km' if dist else '距离: 无')

# 测试多地点
print('\n=== 多地点距离测试 ===')
dist_multi = compute_geo_distance('辽宁沈阳', '北京市,辽宁省', '北京市,沈阳市')
print(f'患者:辽宁沈阳 -> 试验:北京市/北京市 或 辽宁省/沈阳市 -> 最短距离: {dist_multi:.1f} km' if dist_multi else '距离: 无')

# 测试最近地点查找
print('\n=== 最近地点查找 ===')
nearest = find_nearest_location('辽宁沈阳', '北京市,辽宁省', '北京市,沈阳市')
if nearest:
    print(f'最近地点: {nearest["location"]} ({nearest["type"]}) - {nearest["distance"]:.1f} km')
