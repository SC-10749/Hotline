package cn.hotline.domain.execution;

/** 执行目标不存在（工作区、文件等），映射为 404 RESOURCE_NOT_FOUND。 */
public class ExecutionTargetNotFoundException extends RuntimeException {

    public ExecutionTargetNotFoundException(String message) {
        super(message);
    }
}
