PORTAL_FRAME_EXAMPLE = {
    "nodes": """# 节点编号,x,y
N1,0,0
N2,6,0
N3,0,4
N4,6,4
""",
    "elements": """# 单元编号,起点节点,终点节点,E,A,I
E1,N1,N3,2.06e11,0.02,8.5e-5
E2,N3,N4,2.06e11,0.02,8.5e-5
E3,N4,N2,2.06e11,0.02,8.5e-5
""",
    "supports": """# 节点编号,支座类型
# 支座类型: fixed, hinged, roller_x, roller_y
N1,fixed
N2,fixed
""",
    "node_loads": """# 节点编号,Fx,Fy,M
N3,25,0,0
N4,0,-40,0
""",
    "distributed_loads": """# 单元编号,q,方向
# 方向: element, x, y, parallel
E2,-18,element
""",
}


FORMAT_GUIDE = """输入说明

1. 每行一条记录，字段之间用英文逗号分隔。
2. 以 # 开头的行会被忽略，可用于写注释。
3. 请自行保持单位一致，例如 N-m 或 kN-m。
4. 梁柱单元需要输入 E、A、I，程序会自动换算成 anaStruct 需要的 EA 和 EI。
5. 支座类型说明：
   - fixed：固定支座
   - hinged：铰支座
   - roller_x：x 方向可滑动
   - roller_y：y 方向可滑动
6. 分布荷载方向与 anaStruct 保持一致：
   - element：沿单元局部法向
   - parallel：沿单元局部轴向
   - x：全局 x 方向
   - y：全局 y 方向
"""
