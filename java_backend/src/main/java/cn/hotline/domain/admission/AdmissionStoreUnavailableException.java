package cn.hotline.domain.admission;

/** 治理存储不可用（如 Redis 连接失败）。 */
public class AdmissionStoreUnavailableException extends RuntimeException {

    public AdmissionStoreUnavailableException(String message) {
        super(message);
    }

    public AdmissionStoreUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
