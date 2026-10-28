# 沈阳茶饮门店地图与选址辅助系统

基于高德地图POI数据的本地应用，以蜜雪冰城为主要对象，展示沈阳九区茶饮门店和周边设施，并在指定范围内推荐一处值得实地考察的位置。

## 主要功能

- 展示和平、沈河、大东、皇姑、铁西、浑南、于洪、沈北新区及苏家屯九区的门店。
- 按行政区、目标品牌和竞品品牌筛选，点击标记查看名称和地址。
- 学校、住宅、写字楼、商场、地铁、公交、咖啡等设施可独立勾选，默认关闭；使用不同图形区分设施与茶饮店。
- 默认街道底图，可切换空白图；街道地图从本地PMTiles文件读取。
- 在所选行政区或九区内具体地点附近选址，每次推荐一个参考点，固定分析周边一公里的设施与竞争情况。
- 推荐结果包含具体学校、小区、竞品名单和距离；数据不足或没有合适位置时明确说明。

## 技术组成

Python、Flask、SQLite、NumPy、SciPy、原生JavaScript、Leaflet、PMTiles和Protomaps。前端组件放在`static/vendor/`，附有各自许可证，不需要前端构建步骤。

## 首次运行

建议使用Python 3.11或更新版本。以下命令在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

编辑本地`config.yaml`，填写高德开放平台的 **Web服务Key**。该文件已被Git忽略，不应上传。`requirements.lock.txt`记录开发环境版本；需要相同版本时可用它安装。

```powershell
python app.py
```

访问 http://127.0.0.1:8765/ ，使用Ctrl+C停止。Windows也可运行`powershell -File .\start.ps1`后台启动，使用`powershell -File .\stop.ps1`停止。

**仓库只提供代码，不附带采集数据、离线地图包或真实API密钥。** 首次启动会创建空数据库，完整展示需要先准备自己的数据和街道底图。

## 准备门店与设施数据

采集模块通过高德接口获取数据，并保存到`data/research.sqlite3`。前端为展示界面，不提供采集管理入口。配置Key后，可在终端进行小规模采集测试：

```powershell
python -c "from tea_site.collector import collect; print(collect({'brand':'蜜雪冰城','pages':1,'budget':100}))"
```

默认范围为九区，包含边界查询与九类关键词任务。`pages`为每项查询的页数上限，`budget`为本轮请求上限；示例仅用于验证采集流程。按自己的接口权限、配额和研究范围调整采集计划。完成后刷新页面读取最新数据。分页上限或预算可能造成样本不完整，关键词查询不能视作全量普查。

继续已有批次时，采集模块支持`resume`参数；具体参数请参照`tea_site/collector.py`。原始数据与分析结果均保存在本地，不随Git提交。

## 准备街道底图

使用官方区域PMTiles提取工具，详见[离线地图准备](docs/offline-maps.md)。地图数据放在`data/maps/`，不上传到代码仓库。没有本地地图包时，街道背景不可用；空白图仍可用于显示已采集的边界与门店。

## 选址规则

住宅、办公、学校、商场四类设施分别分配相同的类别总权重。候选位置由已知商业设施附近生成，比较其一公里内尚未靠近已有蜜雪冰城的配套，并扣减周边竞品带来的竞争分值。符合设施数量、类别与商业位置条件后，选择评分最高的一处。

结果用于缩小实地考察范围，不是营业额或利润预测。当前分析不包含实际客流、租金和商铺空置状态，一公里为统一的直线距离假设。具体实现见`tea_site/model.py`，结果解释见`tea_site/insights.py`。

## 测试与复算

```powershell
python -m pytest tests -q
node tests/map_filters.cjs
node tests/basemap_loading.cjs
node tests/offline_maps.cjs
node tests/facility_viewport.cjs
python scripts/reproduce.py --dataset 你的本地数据批次ID
```

JavaScript回归检查需要Node.js。复算读取本地快照，输出到`results/`，不会重新请求高德接口。

## 目录

```text
app.py                 本地Web服务与接口
tea_site/              采集、清洗、数据库、空间分析和选址规则
templates/             页面模板
static/                前端代码、样式与第三方地图组件
scripts/               本地结果复算及地图准备脚本
tests/                 Python和JavaScript回归检查
docs/offline-maps.md   地图准备说明
config.example.yaml    不含密钥的配置模板
```

本服务仅面向本机使用，接口限制本机Host并校验写请求令牌。不要直接暴露到公网。地图及组件来源与授权说明保留在地图文档和`static/vendor/LICENSE-*`中。
