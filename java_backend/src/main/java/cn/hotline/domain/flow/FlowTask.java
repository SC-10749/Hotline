package cn.hotline.domain.flow;

import java.util.Map;

/**
 * 流程任务定义：配置中的一个任务项（abjson 中场景下的同名结构）。
 *
 * @param key       任务键（abjson 中场景下的字段名）
 * @param order     执行顺序；相同 order 连续出现时并行执行（沿用 pandora 的 order 语义）
 * @param params    任务参数：abjson 中除 order/fmap 约定字段外的全部字段，
 *                  并注入 {@code _scene}/{@code _task} 供日志与追踪使用
 * @param processor 任务处理器
 */
public record FlowTask(String key, int order, Map<String, Object> params, FlowItemProcessor processor) {
}
