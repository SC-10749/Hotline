package cn.hotline.domain.flow;

/** 流程配置不合法：解析失败、funcmap 缺失、处理器无法实例化等。 */
public class FlowConfigurationException extends RuntimeException {

    public FlowConfigurationException(String message) {
        super(message);
    }

    public FlowConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}
