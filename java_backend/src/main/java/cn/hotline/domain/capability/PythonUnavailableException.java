package cn.hotline.domain.capability;

public class PythonUnavailableException extends RuntimeException {
    public PythonUnavailableException() {
        super("Python capability service is unavailable");
    }
}
