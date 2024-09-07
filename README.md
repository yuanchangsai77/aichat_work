# 自定义AI助手-基于本地数据库知识的大模型应用
## 简介
:robot:自定义助手，知识库记忆检索。用户可在与AI的不断对话中修改记忆内容。

:bulb:本项目启发于[langchain](https://python.langchain.com/en/latest/index.html)、[ai_chat_with_memory](https://github.com/ZeroZY-bgp/ai_chat_with_memory.git)和[:houses:虚拟小镇 Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/pdf/2304.03442.pdf)。

:high_brightness:对话模型需要api key，Embedding模型默认使用[shibing624/text2vec-base-chinese-sentence](https://github.com/shibing624/text2vec)
也可不使用Embedding模型，而使用内置的通过比对字词相似度的算法进行记忆检索（效果不如使用了Embedding模型的算法）。

:ladder:目标建立一个高代码扩展性的知识库问答系统。

安装完成后运行run.bat（对话），edit.bat（编辑）。
## 	:computer:需求
目前文件操作仅支持Windows系统。

使用大模型需要api key，如果使用了本地部署的大模型（包括Embedding），则需关注大模型推理的配置需求。
- Embedding 模型硬件需求

    默认使用的 Embedding 模型 [shibing624/text2vec-base-chinese-sentence](https://github.com/shibing624/text2vec) 约占显存 < 2GB，可修改在 CPU 中运行。

如果是Windows操作系统，此时会通过:open_file_folder:文件管理器打开该世界所在的文件夹。

注：如果自建txt文件，则必须保证是utf-8编码。

运行run.bat，生成URL链接，复制到浏览器或直接点开链接即可开始对话。

### :screwdriver:指令系统
项目内置了指令系统，意在方便对记忆文件进行修改。在聊天界面下方有指令按钮。

### :grey_exclamation:提示词
默认提示词模板位于[此处](template/__init__.py)。对话时会根据检索的记忆对相应板块的标记进行替换。

提示词思想：让大模型以作家的身份进行想象描写，补全人物对话，这样做的效果比让大模型直接进行角色扮演更好。

建议创建初期使用较多人工修改，并多用retry指令生成理想的回答。待回答表现稳定后，可将temperature降低。

### :hammer_and_wrench:高级
dev_settings.ini是开发者设置，将DEBUG_MODE设置为True就能在对话中查看记忆检索的情况，以此辅助记忆文件修改。

如果记忆检索情况或回答不理想，可尝试调整dev_settings.ini的各种参数（也可在界面的config tab中设置）。

包装大模型接口可以参考[此处](agent/llm/__init__.py)，目前支持两种类型的包装方式，一种是本地模型的例子（ChatGLM-6b-int4），另一种是远程模型的例子（GPT3.5）。

## :page_with_curl:To do list
- [x] UI界面（初步）
- [ ] 外接知识库
- [ ] 实时交互系统
- [ ] 重写声音模块，增强声音模块的扩展性
- [ ] 优化记忆检索逻辑
- [ ] 让AI更有时间、空间的观念
- [ ] 加入反思（目前事件记忆是一个简单的替代）
- [ ] 多人对话下的指令系统
- [ ] 多人对话提示词