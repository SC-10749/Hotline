package cn.hotline.domain.execution;

/** 目标状态冲突（如会话已有进行中的运行），映射为 409 INVALID_STATE。 */
public class ExecutionConflictException extends RuntimeException {

    public ExecutionConflictException(String message) {
        super(message);
    }
}
