package cn.hotline.domain.execution;

/** Java 提交结果：申请 ID + 关联运行引用。 */
public record ExecutionSubmissionResult(String requestId, String runId, String status) {
}
