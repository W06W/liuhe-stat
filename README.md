# 六合彩统计工具

基于 Streamlit 开发的六合彩投注统计与结算工具。

## 功能

- 支持多种投注格式输入（特码、平码、生肖、连肖、三中三等）
- 自动解析投注文本，智能识别号码、生肖、金额
- 49号码网格可视化统计
- 生肖投注汇总
- 开奖号码输入后自动计算中奖结果
- 生成结算报告
- 导出 Excel 文件

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 部署

已适配 Streamlit Cloud 部署，推送到 GitHub 后在 [share.streamlit.io](https://share.streamlit.io) 连接仓库即可。
