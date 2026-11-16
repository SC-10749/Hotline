package cn.hotline.api.dto;

import cn.hotline.domain.execution.ExecutionSubmission;
import jakarta.validation.constraints.NotBlank;

/** 执行提交请求载荷（POST /api/v1/execution/requests）。 */
public record ExecutionRequestPayload(
        @NotBlank(message = "conversationId 不能为空") String conversationId,
        String agent,
        @NotBlank(message = "query 不能为空") String query,
        String fileId,
        String agentId,
        String workspaceId) {

    public ExecutionSubmission toSubmission() {
        return new ExecutionSubmission(conversationId, agent, query, fileId, agentId, workspaceId);
    }
}
