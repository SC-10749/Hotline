package cn.hotline.domain.execution;

/** 执行容量不可用（Worker 未运行等），映射为 503 CAPACITY_UNAVAILABLE。 */
public class ExecutionCapacityUnavailableException extends RuntimeException {

    public ExecutionCapacityUnavailableException(String message) {
        super(message);
    }
}
