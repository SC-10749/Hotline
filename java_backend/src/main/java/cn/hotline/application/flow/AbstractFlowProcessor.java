package cn.hotline.application.flow;

import cn.hotline.domain.flow.FlowConfigurationException;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowItemProcessor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;

/**
 * 处理器模板：与 pandora 的 AbstractGeneralProcessor 同构——先检查 toggle
 * 开关（缺省 "1" 表示启用，配置 toggle=0 时跳过），再执行 doProcess，
 * 并记录任务耗时。结果通过 FlowContext 交换。
 */
public abstract class AbstractFlowProcessor implements FlowItemProcessor {

    private final Logger log = LoggerFactory.getLogger(getClass());

    @Override
    public final void process(FlowContext context, Map<String, Object> params) throws Exception {
        if (!enabled(params, "toggle", "1")) {
            log.debug("任务 {} 已通过 toggle 关闭，跳过", params.get("_task"));
            return;
        }
        long start = System.nanoTime();
        doProcess(context, params);
        log.debug("场景 {} 任务 {} 完成，耗时 {} ms", params.get("_scene"), params.get("_task"),
                (System.nanoTime() - start) / 1_000_000L);
    }

    protected abstract void doProcess(FlowContext context, Map<String, Object> params) throws Exception;

    /** 开关检查：参数值为 "0" 时关闭，其余（含缺省）视为开启。 */
    protected boolean enabled(Map<String, Object> params, String paramKey, String defaultValue) {
        Object value = params.get(paramKey);
        String text = value == null ? defaultValue : String.valueOf(value);
        return !"0".equals(text.trim());
    }

    /** 读取字符串参数。 */
    protected String stringParam(Map<String, Object> params, String key, String defaultValue) {
        Object value = params.get(key);
        return value == null ? defaultValue : String.valueOf(value);
    }

    /** 读取整数参数（兼容 abjson 中 "0"/"1" 风格的字符串写法）。 */
    protected int intParam(Map<String, Object> params, String key, int defaultValue) {
        Object value = params.get(key);
        if (value == null) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(String.valueOf(value).trim());
        } catch (NumberFormatException exception) {
            throw new FlowConfigurationException("任务参数 " + key + " 不是整数：" + value);
        }
    }

    /** 读取布尔参数。 */
    protected boolean booleanParam(Map<String, Object> params, String key, boolean defaultValue) {
        Object value = params.get(key);
        if (value == null) {
            return defaultValue;
        }
        return Boolean.parseBoolean(String.valueOf(value).trim());
    }
}
