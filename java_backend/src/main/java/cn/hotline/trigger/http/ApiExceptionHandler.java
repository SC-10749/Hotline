package cn.hotline.trigger.http;

import cn.hotline.api.dto.ApiError;
import cn.hotline.domain.admission.AdmissionStoreUnavailableException;
import cn.hotline.domain.admission.QuotaExceededException;
import cn.hotline.domain.capability.PythonUnavailableException;
import cn.hotline.domain.execution.ExecutionCapacityUnavailableException;
import cn.hotline.domain.execution.ExecutionConflictException;
import cn.hotline.domain.execution.ExecutionInvalidArgumentException;
import cn.hotline.domain.execution.ExecutionTargetNotFoundException;
import cn.hotline.domain.flow.FlowConfigurationException;
import cn.hotline.domain.flow.FlowExecutionException;
import cn.hotline.domain.flow.FlowNotFoundException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 统一错误契约：{code, message} 封套与 HTTP 状态码映射。 */
@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(PythonUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public ApiError pythonUnavailable() {
        return new ApiError("PYTHON_UNAVAILABLE", "Python 能力服务暂不可用");
    }

    @ExceptionHandler(AdmissionStoreUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public ApiError admissionStoreUnavailable() {
        return new ApiError("DEPENDENCY_UNAVAILABLE", "接入治理依赖暂不可用");
    }

    @ExceptionHandler(ExecutionInvalidArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiError invalidArgument(ExecutionInvalidArgumentException exception) {
        return new ApiError("INVALID_ARGUMENT", messageOrDefault(exception, "参数不合法"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiError validation(MethodArgumentNotValidException exception) {
        String message = exception.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .map(error -> error.getDefaultMessage() == null || error.getDefaultMessage().isBlank()
                        ? error.getField() + " 参数不合法"
                        : error.getDefaultMessage())
                .orElse("参数校验失败");
        return new ApiError("INVALID_ARGUMENT", message);
    }

    @ExceptionHandler(ExecutionTargetNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public ApiError targetNotFound(ExecutionTargetNotFoundException exception) {
        return new ApiError("RESOURCE_NOT_FOUND", messageOrDefault(exception, "目标资源不存在"));
    }

    @ExceptionHandler(ExecutionConflictException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    public ApiError conflict(ExecutionConflictException exception) {
        return new ApiError("INVALID_STATE", messageOrDefault(exception, "目标状态不允许该操作"));
    }

    @ExceptionHandler(ExecutionCapacityUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public ApiError capacityUnavailable(ExecutionCapacityUnavailableException exception) {
        return new ApiError("CAPACITY_UNAVAILABLE", messageOrDefault(exception, "执行服务容量不足"));
    }

    @ExceptionHandler(QuotaExceededException.class)
    @ResponseStatus(HttpStatus.TOO_MANY_REQUESTS)
    public ApiError quotaExceeded(QuotaExceededException exception) {
        return new ApiError("QUOTA_EXCEEDED", messageOrDefault(exception, "配额已用尽"));
    }

    @ExceptionHandler(FlowNotFoundException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public ApiError flowNotFound() {
        return new ApiError("FLOW_UNAVAILABLE", "编排场景未就绪");
    }

    @ExceptionHandler(FlowConfigurationException.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public ApiError flowConfiguration(FlowConfigurationException exception) {
        log.error("流程配置错误", exception);
        return new ApiError("INTERNAL", "服务内部错误");
    }

    @ExceptionHandler(FlowExecutionException.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public ApiError flowExecution(FlowExecutionException exception) {
        log.error("流程执行失败", exception);
        return new ApiError("INTERNAL", "服务内部错误");
    }

    private static String messageOrDefault(RuntimeException exception, String fallback) {
        String message = exception.getMessage();
        return message == null || message.isBlank() ? fallback : message;
    }
}
