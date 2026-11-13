package cn.hotline.domain.execution;

/** 执行提交：Java 侧接收的提交参数（与 Python /execution/runs 载荷对齐）。 */
public record ExecutionSubmission(
        String conversationId,
        String agent,
        String query,
        String fileId,
        String agentId,
        String workspaceId) {
}
