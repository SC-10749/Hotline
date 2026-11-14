package cn.hotline.application.flow.task;

import cn.hotline.application.flow.AbstractFlowProcessor;
import cn.hotline.domain.execution.ExecutionInvalidArgumentException;
import cn.hotline.domain.execution.ExecutionSubmission;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import org.springframework.stereotype.Component;

import java.util.Map;

/**
 * 提交参数校验与规范化：必填校验、query 长度上限（maxQueryLength 任务参数）、
 * agent 缺省 "chat"。校验失败抛 ExecutionInvalidArgumentException（400）。
 */
@Component
public class ValidateSubmissionProcessor extends AbstractFlowProcessor {

    private static final int DEFAULT_MAX_QUERY_LENGTH = 20_000;

    @Override
    protected void doProcess(FlowContext context, Map<String, Object> params) {
        ExecutionSubmission submission = context.require(FlowKeys.SUBMISSION, ExecutionSubmission.class);
        if (isBlank(submission.conversationId())) {
            throw new ExecutionInvalidArgumentException("conversationId 不能为空");
        }
        if (isBlank(submission.query())) {
            throw new ExecutionInvalidArgumentException("query 不能为空");
        }
        int maxQueryLength = intParam(params, "maxQueryLength", DEFAULT_MAX_QUERY_LENGTH);
        if (submission.query().length() > maxQueryLength) {
            throw new ExecutionInvalidArgumentException("query 长度不能超过 " + maxQueryLength);
        }
        String agent = isBlank(submission.agent()) ? "chat" : submission.agent().trim();
        context.put(FlowKeys.SUBMISSION, new ExecutionSubmission(
                submission.conversationId().trim(),
                agent,
                submission.query().trim(),
                trimToNull(submission.fileId()),
                trimToNull(submission.agentId()),
                trimToNull(submission.workspaceId())));
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
