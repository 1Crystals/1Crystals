# AnythingLLM 文档上传与向量化页面

单文件网页，向 AnythingLLM 服务器的**第一个工作区**上传文档，上传后自动完成向量化嵌入
（服务端侧切分 chunk 并写入向量库），无需前端自行调用 embedding 模型。

## 使用

```bash
python start.py          # 默认端口 5500，自动打开浏览器
python start.py 8080     # 指定端口
```

也可以直接双击打开 `index.html`（AnythingLLM 服务端已开启 CORS，跨源请求可直连）。

页面打开后在「连接配置」填入服务器地址与 API Key，点「测试连接」。

## 使用的接口

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 验证密钥 | GET | `/api/v1/auth` |
| 获取工作区（取第一个） | GET | `/api/v1/workspaces` |
| **上传文档并嵌入工作区** | POST | `/api/v1/document/upload` |
| 查看工作区文档 | GET | `/api/v1/workspace/{slug}` |
| 全局向量数 | GET | `/api/v1/system/vector-count` |

认证头为 `Authorization: Bearer <API Key>`（AnythingLLM 的 `BearerAuth` 方案，非 `sk-` 形式）。

## 向量化是怎么完成的

上传时通过 multipart 表单携带 `addToWorkspaces=<工作区slug>`：

```bash
curl -X POST http://localhost:3001/api/v1/document/upload \
  -H "Authorization: Bearer <API_KEY>" \
  -F "file=@report.pdf" \
  -F "addToWorkspaces=<workspace-slug>" \
  -F 'metadata={"title":"季度报告","docAuthor":"张三"}'
```

`addToWorkspaces` 让 AnythingLLM 在接收文件的同一次请求内完成
「解析 → 切块 → embedding → 写入该工作区向量索引」，因此不需要额外调用
`/v1/workspace/{slug}/update-embeddings`。

`metadata` 仅接受 `title`、`docAuthor`、`description`、`docSource` 四个键；
若服务端对 `metadata` 返回 422，页面会自动去掉该字段重试一次。

## 页面功能

- 连接测试与密钥校验（配置存本地 localStorage）
- 工作区列表加载，**默认选中第一个工作区**
- 拖拽 / 点选批量上传，逐文件串行上传，失败不中断
- 可选元数据（标题、作者、来源、描述）
- 实时进度条、字数 / Token 估算、工作区归属
- 上传后自动刷新全局向量数与工作区文档列表以确认嵌入结果
- 运行日志面板

## 兼容性说明

AnythingLLM 的工作区路径是**单数** `/v1/workspace/{slug}`（列表接口才是复数 `/v1/workspaces`）；
文档列表接口是复数 `/v1/documents`，其余文档接口为单数 `/v1/document/*`。

不同版本的工作区文档对象字段略有差异，页面已做兼容处理：
标题优先取 `metadata` 解析结果，回退到 `filename`。

## 注意

页面内含明文 API Key，仅适用于本地/内网可信环境。若要对外提供服务，
应在服务端加一层代理，不要把 Key 下发到浏览器。