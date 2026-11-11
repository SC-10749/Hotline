package cn.hotline.trigger.http;

import cn.hotline.api.dto.ApiError;
import cn.hotline.domain.capability.PythonUnavailableException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(PythonUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    public ApiError pythonUnavailable() {
        return new ApiError("PYTHON_UNAVAILABLE", "Python 能力服务暂不可用");
    }
}
