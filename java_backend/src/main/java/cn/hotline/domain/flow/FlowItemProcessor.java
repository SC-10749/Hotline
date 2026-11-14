package cn.hotline.domain.flow;

import java.util.Map;

/**
 * 流程任务处理器。对应 pandora-search-music 的 ItemWithParamsProcessor：
 * 处理结果通过约定的上下文键交换，而不是通过返回值传递。
 */
@FunctionalInterface
public interface FlowItemProcessor {

    void process(FlowContext context, Map<String, Object> params) throws Exception;
}
