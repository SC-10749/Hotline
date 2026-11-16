package cn.hotline.domain.flow;

/** 运行期未找到指定场景。 */
public class FlowNotFoundException extends RuntimeException {

    public FlowNotFoundException(String message) {
        super(message);
    }
}
