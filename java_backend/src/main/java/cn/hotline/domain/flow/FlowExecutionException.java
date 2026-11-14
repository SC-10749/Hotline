package cn.hotline.domain.flow;

/** 流程执行期错误：受检异常包装、上下文缺少产物等。 */
public class FlowExecutionException extends RuntimeException {

    public FlowExecutionException(String message) {
        super(message);
    }

    public FlowExecutionException(String message, Throwable cause) {
        super(message, cause);
    }
}
