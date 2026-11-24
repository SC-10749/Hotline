package cn.hotline.domain.capability;

public class PythonUnavailableException extends RuntimeException {
    public PythonUnavailableException() {
        this("Python 能力服务暂不可用");
    }

    public PythonUnavailableException(String diagnostic) {
        super(diagnostic);
    }
}
