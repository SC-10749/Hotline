package cn.hotline.application.flow.task;

import cn.hotline.application.admission.SubmissionLedger;
import cn.hotline.application.flow.AbstractFlowProcessor;
import cn.hotline.domain.admission.QuotaExceededException;
import cn.hotline.domain.flow.FlowContext;
import cn.hotline.domain.flow.FlowKeys;
import cn.hotline.infrastructure.config.AdmissionProperties;
import org.springframework.stereotype.Component;

import java.util.Map;

/** 提交配额检查：按客户端统计当日提交次数（hotline.admission.submission-quota-per-day，0 表示不限）。 */
@Component
public class SubmissionQuotaProcessor extends AbstractFlowProcessor {

    private final SubmissionLedger submissionLedger;
    private final AdmissionProperties admissionProperties;

    public SubmissionQuotaProcessor(SubmissionLedger submissionLedger, AdmissionProperties admissionProperties) {
        this.submissionLedger = submissionLedger;
        this.admissionProperties = admissionProperties;
    }

    @Override
    protected void doProcess(FlowContext context, Map<String, Object> params) {
        long quota = admissionProperties.submissionQuotaPerDay();
        if (quota <= 0) {
            return;
        }
        String clientKey = context.require(FlowKeys.CLIENT_KEY, String.class);
        if (submissionLedger.exceeded(clientKey, quota)) {
            throw new QuotaExceededException("当日提交次数已达上限（" + quota + " 次）");
        }
    }
}
