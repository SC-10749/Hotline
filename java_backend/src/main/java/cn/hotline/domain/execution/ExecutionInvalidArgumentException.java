package cn.hotline.domain.execution;

/** 提交参数不合法，映射为 400 INVALID_ARGUMENT。 */
public class ExecutionInvalidArgumentException extends RuntimeException {

    public ExecutionInvalidArgumentException(String message) {
        super(message);
    }
}
