import copy# 深拷贝
import os# 操作系统
import random# 随机数
import threading# 线程
import time# 时间
import openai# openai

from tools.store import SimpleStoreTool, VectorStoreTool# 存储模块
from tools.text import high_word_similarity_text_filter# 文本过滤
from tools.utils import load_txt_to_lst, load_last_n_lines, append_to_str_file, openai_moderation, CharacterInfo# 工具函数
from command import debug_msg_pool# 调试信息池
from config import DevConfig# 配置

# 收集上下文
def collect_context(text_lst):
    return "\n".join([text for text in text_lst])# 使用换行符连接列表中的所有文本

# 主代理类
class MainAgent:
    def __init__(self,
                 llm,
                 embed_model,
                 config):
        """
        :param ai: 助手
        :param llm: 大模型实例
        :param embed_model: 记忆检索使用的文本转向量模型实例
        :param config: 基本设置(config.ini)
        """
        # ---基本设置参数
        self.base_config = config
        self.info = CharacterInfo()#在utils.py中定义

        # ------高级开发参数
        self.dev_config = DevConfig()#在config.py中定义

        # ---暂存区，有查询，实体，对话，最后答案，步长
        self.query = ''
        self.entity_text = ''
        self.dialog_text = ''
        self.last_ans = ''
        self.step = 1
        # ---

        # 嵌入模型
        self.embeddings = embed_model
        if self.embeddings is None:
            self.use_embed_model = False
        else:
            self.use_embed_model = True
        # 存储工具
        self.store_tool = self.load_store_tool()
        self.entity_store = self.store_tool.load_entity_store()
        self.history_store = self.store_tool.load_history_store()

        self.llm = llm
        # 历史对话列表
        self.history = []
        # 初始化提示语
        self.basic_history = load_txt_to_lst(self.info.prompt_path)
        self.cur_prompt = self.basic_history[0][0]
        # 加载对话窗口
        self.load_history(self.basic_history)
        # 窗口控制变量
        self.total_token_size = 0

    # 重置历史
    def reset_history(self, info):
        # 历史对话列表
        self.history = []
        # 初始化提示语
        self.basic_history = load_txt_to_lst(info.prompt_path)
        self.cur_prompt = self.basic_history[0][0]
        # 加载短期对话历史
        self.load_history(self.basic_history)

    def reload_config(self, config):
        self.base_config = config
        # 模型参数
        self.llm.set_para(temperature=config.temperature,
                          max_token=config.dialog_max_token,
                          model_name=config.model_name,
                          streaming=config.streaming)
        # 记忆检索工具
        self.store_tool = self.load_store_tool()
        self.entity_store = self.store_tool.load_entity_store()
        self.history_store = self.store_tool.load_history_store()

    # 重新加载开发配置
    def reload_dev_config(self):
        self.dev_config = DevConfig()


    # 加载存储工具
    def load_store_tool(self):
        if self.use_embed_model:
            # 向量存储
            return VectorStoreTool(self.info,
                                   self.embeddings,
                                   self.base_config.entity_top_k,
                                   self.base_config.history_top_k,
                                   self.base_config.event_top_k)
        else:
            # 简单存储
            return SimpleStoreTool(self.info,
                                   self.base_config.entity_top_k,
                                   self.base_config.history_top_k,
                                   self.base_config.event_top_k)

    # 获取临时查询
    def get_tmp_query(self):
        return self.query

    # 获取最后答案
    def get_last_ans(self):
        return self.last_ans

    # 聊天
    def chat(self, query):
        # 文本中加入提问者身份
        q_start = self.user_name + "说：" if self.user_name != '' else ''
        # ------检索记忆（实体、对话、事件）
        # 获取上文窗口
        entity_lst, dialog_lst= self.get_related(self.get_context_window(q_start + query))
        # 嵌入提示词
        self.entity_text = collect_context(entity_lst)
        self.dialog_text = collect_context(dialog_lst)
        context_len = self.embedding_context(self.entity_text, self.dialog_text, self.event_text)
        # ------

        # 安全性检查
        if self.llm.__class__.__name__ == "Gpt3_5LLM" \
                and self.dev_config.openai_text_moderate \
                and openai_moderation(self.history[:1], q_start + query):
            print("WARN: openai使用协议")
            debug_msg_pool.append_msg("WARN: openai使用协议")
            return 'no result'

        # ---与大模型通信
        ans = ''
        # total_query = q_start + query + ' ' + self.ai_name + '说：'
        total_query = q_start + query
        if self.base_config.streaming:
            for content in self.llm.chat(total_query, self.history):
                ans += content
                yield content
        else:
            ans = self.llm.chat(total_query, self.history)
            yield ans

        if self.llm.__class__.__name__ == "Gpt3_5LLM" \
                and self.dev_config.openai_text_moderate:
            res = openai.Moderation.create(input=ans)
            if res["results"][0]["flagged"]:
                print(res["results"][0])
                print("WARN: openai使用协议")
                debug_msg_pool.append_msg(res["results"][0] + '\n' + "WARN: openai使用协议")
        # ---

        # ---处理对话历史
        self.cur_prompt = self.history[0][0]
        # 如果开头已经有"xxx说"，则不补全ai名字
        if ans.startswith(self.ai + '说：') or ans.startswith(self.ai + '说:'):
            final_ans = ans
        else:
            final_ans = self.ai + '说：' + ans
        self.history.append((q_start + query, final_ans))

        # 计算当前使用的token数
        self.calc_token_size()

        print("Token size:", self.total_token_size)
        debug_msg_pool.append_msg("Token size:" + str(self.total_token_size))

        # 恢复最开头的提示词
        self.history[0] = self.basic_history[0]

        if not self.base_config.lock_memory:
            # 保存新对话到文件中
            dialog = q_start + query + ' ' + final_ans + '\n'
            append_to_str_file(self.info.history_path, dialog)
        self.last_ans = ans
        # 窗口控制
        self.history_window_control(context_len)
        # ---
        # if not self.ui_enabled:
        #     p_ans = self.ai_name + '：' + ans + '\n'
        #     if self.base_config.streaming:
        #         if self.base_config.voice_enabled:
        #             voice_thread = threading.Thread(target=self.voice_module.say, args=(ans,))
        #             voice_thread.start()
        #         p_ans = self.ai_name + '：' + ans + '\n'
        #         word_count = 0
        #         for c in p_ans:
        #             print(c, end='', flush=True)
        #             time.sleep(0.2)
        #             word_count += 1
        #             if word_count >= self.base_config.words_per_line:
        #                 print()
        #                 word_count = 0
        #         print()
        #         if self.base_config.voice_enabled:
        #             voice_thread.join()
        #     else:
        #         for i in range(0, len(p_ans), self.base_config.words_per_line):
        #             print(p_ans[i:i + self.base_config.words_per_line])
        #         if self.voice_enabled:
        #             self.voice_module.say(ans)
        # 临时存储当前提问
        self.query = query
        return ans

    # 计算token大小
    def calc_token_size(self):
        self.total_token_size = 0
        for dialog in self.history:
            self.total_token_size += (len(dialog[0]) + len(dialog[1]))

    # 获取上下文窗口
    def get_context_window(self, query):
        lines = load_last_n_lines(self.info.history_path, self.dev_config.similarity_comparison_context_window - 1)
        comparison_string = ' '.join(line for line in lines)
        comparison_string += query
        return comparison_string

    # 历史对话窗口控制
    def history_window_control(self, context_len):
        if self.total_token_size + context_len >= self.base_config.window_max_token:
            while self.total_token_size + context_len > \
                    (self.base_config.window_max_token - self.base_config.token_decrease):
                try:
                    self.total_token_size -= (len(self.history[1][0]) + len(self.history[1][1]))
                    self.history.pop(1)
                except IndexError:
                    # print("窗口不能再缩小了")
                    break
            if self.dev_config.DEBUG_MODE:
                print("窗口缩小， 历史对话：")
                debug_msg_pool.append_msg("窗口缩小， 历史对话：")
                for dialog in self.history:
                    print(dialog[0], end=' ')
                    print(dialog[1])
                    debug_msg_pool.append_msg(dialog[0] + ' ' + dialog[1])

    # 加载历史记录
    def load_history(self, basic_history):
        self.basic_history = basic_history
        if os.path.exists(self.info.history_path) and os.path.getsize(self.info.history_path) == 0:
            # 历史记录为空
            self.history = copy.deepcopy(self.basic_history)
        else:
            self.history = copy.deepcopy(self.basic_history)
            # 加载历史记录最后几行
            history_lst = load_last_n_lines(self.info.history_path, self.base_config.history_window)
            splitter = self.info.ai_name + '说'
            for dialog in history_lst:
                first_index = dialog.find(splitter)
                second_index = dialog.find(splitter, first_index + len(splitter))
                if second_index != -1:
                    # 两次AI回复，说明是继续回答
                    tuple_result = (dialog[:second_index], dialog[second_index:])
                else:
                    tuple_result = (dialog[:first_index], dialog[first_index:])
                self.history.append(tuple_result)
        self.history_store = self.store_tool.load_history_store()

    # 嵌入上下文
    def embedding_context(self, entity, dialog, event):

        context = self.history[0][0]
        context = context.replace("{{{ENTITY}}}", entity)
        context = context.replace("{{{DIALOG}}}", dialog)

        first_ans = self.history[0][1].replace("{{{AI}}}", self.ai)

        context_len = len(entity) + len(dialog)
        if self.dev_config.DEBUG_MODE:
            print("context长度:", context_len)
            print("提示词总长度:", len(context))
            debug_msg_pool.append_msg("context长度:" + str(context_len))
            debug_msg_pool.append_msg("提示词总长度:" + str(len(context)))

        self.history[0] = (context, first_ans)

        if self.dev_config.DEBUG_MODE:
            print("实体记忆：")
            print(entity)
            debug_msg_pool.append_msg(entity)
            print("对话记忆：")
            print(dialog)
            debug_msg_pool.append_msg(dialog)
        return context_len

    # 获取相关记忆
    def get_related(self, query):

        entity_mem = self.store_tool.get_entity_mem(query, self.entity_store)

        if self.dev_config.fragment_answer:
            # 打碎实体策略
            entity_mem = self.store_tool.entity_fragment(query, entity_mem)

        # 字词高相似度去重
        entity_mem = high_word_similarity_text_filter(self, entity_mem)

        if not self.base_config.lock_memory and self.step >= self.dev_config.update_history_store_step:
            self.history_store = self.store_tool.load_history_store()
            self.step = 1
            if self.dev_config.DEBUG_MODE:
                print("History store updated.")
                debug_msg_pool.append_msg("History store updated.")

        self.step += 1

        dialog_mem = self.store_tool.get_history_mem(query, self.history_store)

        if self.dev_config.answer_extract_enabled:
            # 仅提取AI回答
            self.store_tool.answer_extract(dialog_mem, has_ai_name=not self.dev_config.fragment_answer)
            if self.dev_config.fragment_answer:
                # 打碎AI回答策略
                dialog_mem = self.store_tool.dialog_fragment(query, dialog_mem)

        dialog_mem = high_word_similarity_text_filter(self, dialog_mem)

        # 随机打乱列表，shuffle是随机打乱列表的函数
        random.shuffle(entity_mem)
        random.shuffle(dialog_mem)

        return entity_mem, dialog_mem
