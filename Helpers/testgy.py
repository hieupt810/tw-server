import time
import math
from geopy.distance import geodesic, great_circle

def benchmark_all_methods(points, iterations=1000):
    """So sánh tất cả phương pháp tính khoảng cách"""
    
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        return R * 2 * math.asin(math.sqrt(a))
    
    n = len(points)
    results = {}
    
    print(f"Benchmark với {n} điểm, {iterations} iterations")
    print(f"Số phép tính khoảng cách mỗi iteration: {n*(n-1)//2}")
    print("="*50)
    
    # 1. Haversine manual
    start = time.time()
    haversine_distances = []
    for _ in range(iterations):
        for i in range(n):
            for j in range(i+1, n):
                dist = haversine(points[i][0], points[i][1], points[j][0], points[j][1])
                if _ == 0:  # Lưu kết quả của iteration đầu tiên
                    haversine_distances.append(dist)
    results['Haversine Manual'] = time.time() - start
    
    # 2. GeoPy Great Circle
    start = time.time()
    great_circle_distances = []
    for _ in range(iterations):
        for i in range(n):
            for j in range(i+1, n):
                dist = great_circle(points[i], points[j]).kilometers
                if _ == 0:
                    great_circle_distances.append(dist)
    results['GeoPy Great Circle'] = time.time() - start
    
    # 3. GeoPy Geodesic
    start = time.time()
    geodesic_distances = []
    for _ in range(iterations):
        for i in range(n):
            for j in range(i+1, n):
                dist = geodesic(points[i], points[j]).kilometers
                if _ == 0:
                    geodesic_distances.append(dist)
    results['GeoPy Geodesic'] = time.time() - start
    
    # In kết quả performance
    print("=== PERFORMANCE COMPARISON ===")
    fastest_time = min(results.values())
    for method, time_taken in results.items():
        slowdown = time_taken / fastest_time
        print(f"{method:20}: {time_taken:.4f}s (x{slowdown:.1f})")
    
    # So sánh độ chính xác chi tiết
    print("\n=== ACCURACY COMPARISON ===")
    
    # So sánh một số cặp điểm điển hình
    test_pairs = [
        (0, 1, "Hà Nội - TP.HCM"),
        (0, 2, "Hà Nội - Đà Nẵng"), 
        (1, 5, "TP.HCM - Nha Trang"),
        (2, 7, "Đà Nẵng - Huế"),
        (0, 9, "Hà Nội - Lào Cai")
    ]
    
    for i, j, name in test_pairs:
        idx = get_matrix_index(i, j, n)
        h_dist = haversine_distances[idx]
        gc_dist = great_circle_distances[idx]
        geo_dist = geodesic_distances[idx]
        
        print(f"\n{name}:")
        print(f"  Haversine Manual:  {h_dist:.2f} km")
        print(f"  GeoPy Great Circle: {gc_dist:.2f} km")
        print(f"  GeoPy Geodesic:    {geo_dist:.2f} km")
        print(f"  Chênh lệch H vs Geo: {abs(h_dist - geo_dist):.2f} km ({abs(h_dist - geo_dist)/geo_dist*100:.2f}%)")
    
    # Thống kê tổng thể
    print("\n=== OVERALL STATISTICS ===")
    haversine_vs_geodesic = [abs(h - g) for h, g in zip(haversine_distances, geodesic_distances)]
    great_circle_vs_geodesic = [abs(gc - g) for gc, g in zip(great_circle_distances, geodesic_distances)]
    
    print(f"Chênh lệch trung bình Haversine vs Geodesic: {sum(haversine_vs_geodesic)/len(haversine_vs_geodesic):.2f} km")
    print(f"Chênh lệch tối đa Haversine vs Geodesic: {max(haversine_vs_geodesic):.2f} km")
    print(f"Chênh lệch trung bình Great Circle vs Geodesic: {sum(great_circle_vs_geodesic)/len(great_circle_vs_geodesic):.2f} km")
    
    return results, haversine_distances, great_circle_distances, geodesic_distances

def get_matrix_index(i, j, n):
    """Tính index trong mảng 1D cho ma trận tam giác trên"""
    if i > j:
        i, j = j, i
    return i * n - i * (i + 1) // 2 + j - i - 1

# Test với 15 điểm Việt Nam
test_points_15 = [
    (21.0285, 105.8542),  # 0. Hà Nội
    (10.8231, 106.6297),  # 1. TP.HCM
    (16.0471, 108.2068),  # 2. Đà Nẵng
    (20.8449, 106.6881),  # 3. Hải Phòng
    (10.0452, 105.7469),  # 4. Cần Thơ
    (12.2388, 109.1967),  # 5. Nha Trang
    (11.9404, 108.4583),  # 6. Đà Lạt
    (14.0583, 108.2772),  # 7. Huế
    (15.8801, 108.338),   # 8. Hội An
    (22.3964, 103.8437),  # 9. Lào Cai
    (9.1790, 105.1524),   # 10. Rạch Giá
    (13.4125, 109.2198),  # 11. Quy Nhon
    (17.9762, 106.3247),  # 12. Quảng Trị
    (18.3351, 105.9045),  # 13. Vinh
    (21.5944, 105.9772),  # 14. Bắc Ninh
]

# Chạy benchmark
results, h_distances, gc_distances, geo_distances = benchmark_all_methods(test_points_15, iterations=50)

print("\n" + "="*60)
print("RECOMMENDATION FOR TSP:")
print("="*60)