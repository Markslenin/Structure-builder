# Structure Builder

一个基于 `anaStruct` 的轻量结构建模与结果查看工具，当前界面使用 `PySide6 Widgets` 实现，适合做二维杆系结构的快速建模、示意、教学演示和初步结果查看。

## 项目特点

- 基于 `anaStruct` 进行结构求解
- 支持节点、杆件、支座、节点力、集中力偶、分布荷载
- 支持整数网格吸附与画布交互建模
- 支持结构图、位移图、轴力图、剪力图、弯矩图、反力图切换
- 支持右侧属性面板直接编辑当前选中对象
- 采用 `PySide6` 停靠面板布局，适合后续继续扩展

## 技术栈

- Python 3.10+
- `anaStruct`
- `PySide6`
- `matplotlib`

## 目录结构

```text
struct/
├─ run_gui.py
├─ pyproject.toml
├─ README.md
└─ src/
   └─ anastruct_simple_app/
      ├─ __init__.py
      ├─ __main__.py
      ├─ models.py
      ├─ parsers.py
      ├─ solver.py
      ├─ qt_styles.py
      ├─ qt_ui.py
      ├─ ui.py
      └─ examples.py
```

## 安装

在项目根目录执行：

```bash
pip install -e .
```

如果你使用虚拟环境，也可以先激活虚拟环境后再安装。

## 运行

方式 1：

```bash
python run_gui.py
```

方式 2：

```bash
python -m anastruct_simple_app
```

方式 3：

```bash
anastruct-simple-app
```

## 当前能力

目前主要支持以下建模与结果查看流程：

1. 在画布上放置节点
2. 连接杆件形成结构
3. 为节点添加支座
4. 为节点添加集中力或集中力偶
5. 通过两个节点选择分布荷载作用区段
6. 点击 `Solve` 查看结果

## 项目声明

- 本项目是个人学习与工程工具探索性质的二次开发项目。
- 本项目基于 `anaStruct` 进行结构求解，但并非 `anaStruct` 官方项目。
- 本仓库的界面层、交互层与工程组织方式为独立实现。

## 免责声明

- 本项目结果仅适用于学习、教学演示、概念验证和初步分析参考。
- 不建议直接将本项目计算结果作为正式施工图、审图、校核或安全责任依据。
- 在正式工程场景中，请务必由具备资质的专业工程师进行独立复核与判断。
- 使用者应自行保证输入参数、单位体系、边界条件与荷载工况的正确性。

## 说明

- 请保持单位一致，例如统一采用 `N-m`、`kN-m` 或其他完整单位体系。
- `anaStruct` 的某些结果字段在不同版本中可能存在差异，项目已做一定兼容处理。
- 若图形显示不可用，请确认环境中已正确安装 `matplotlib`。
- 若使用 GitHub 发布，建议同时提交 `.gitignore`，避免上传 `.venv`、IDE 配置和缓存文件。

## 参考资料

- [anaStruct Documentation](https://anastruct.readthedocs.io/en/latest/)
- [Loads](https://anastruct.readthedocs.io/en/latest/loads.html)
- [Elements](https://anastruct.readthedocs.io/en/latest/elements.html)
- [Plotting](https://anastruct.readthedocs.io/en/latest/plotting.html)
- [Post processing](https://anastruct.readthedocs.io/en/latest/post_processing.html)
