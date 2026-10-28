# 离线街道地图准备

页面提供街道图和空白图。代码仓库不包含地图数据包，也不包含地图提取工具的可执行文件。

## 文件位置

街道底图放置在`data/maps/shenyang-streets.pmtiles`。Flask提供支持HTTP Range的本地读取接口，浏览器按需获取内容。数据目录已经加入Git忽略规则。

## 准备工具与数据

1. 从[go-pmtiles官方发布页](https://github.com/protomaps/go-pmtiles/releases)下载Windows工具。本项目原开发环境使用v1.31.2。
2. 将工具解压为`scripts/bin/pmtiles.exe`，按发布包保留工具许可证。
3. 使用[Protomaps官方数据源](https://source.coop/protomaps/openstreetmap)进行区域提取。以下命令只准备街道地图：

```powershell
New-Item -ItemType Directory -Force data/maps, work/map-build
scripts/bin/pmtiles.exe extract https://data.source.coop/protomaps/openstreetmap/v4.pmtiles work/map-build/overview.pmtiles --bbox=120,39,127,45 --maxzoom=10 --download-threads=4
scripts/bin/pmtiles.exe extract https://data.source.coop/protomaps/openstreetmap/v4.pmtiles work/map-build/detail.pmtiles --bbox=122.2,41.1,124.2,43.2 --minzoom=11 --maxzoom=15 --download-threads=4
scripts/bin/pmtiles.exe merge work/map-build/overview.pmtiles work/map-build/detail.pmtiles work/map-build/shenyang-streets.pmtiles
scripts/bin/pmtiles.exe verify work/map-build/shenyang-streets.pmtiles
```

验证成功后，将生成文件复制到`data/maps/shenyang-streets.pmtiles`。更新已有地图前先停止应用，并备份原文件。数据源和工具参数可能随上游版本变化，详见[官方地图下载文档](https://docs.protomaps.com/basemaps/downloads)。下载需要联网和足够磁盘空间，普通应用启动不会自动下载。

`scripts/download_basemaps.py`是原开发阶段的完整准备脚本，除街道外还会提取历史地形资源；当前前端不显示地形图，仅需街道文件，可使用上面的街道提取流程。

## 范围与来源

详细包围框覆盖沈阳市及部分周边，低级别概览范围更广。前端按九区行政边界遮罩显示，选址仍限定九区。街道数据最高15级，进一步放大为显示放大。

底图来自OpenStreetMap和Natural Earth，经Protomaps提供。使用时保留[OpenStreetMap署名与授权信息](https://www.openstreetmap.org/copyright)及地图组件中的来源标识。这里使用官方支持的区域文件提取方式，不批量抓取公共图片瓦片服务器。

地图显示、已有数据查询和已有数据选址可在本地完成；高德地点搜索和新的数据采集仍需网络与API Key。
