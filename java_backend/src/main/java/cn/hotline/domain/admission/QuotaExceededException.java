package cn.hotline.domain.admission;

/** 配额超限（提交配额等），映射为 429 QUOTA_EXCEEDED。 */
public class QuotaExceededException extends RuntimeException {

    public QuotaExceededException(String message) {
        super(message);
    }
}
