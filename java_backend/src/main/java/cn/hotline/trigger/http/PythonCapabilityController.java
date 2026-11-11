package cn.hotline.trigger.http;

import java.io.IOException;
import cn.hotline.infrastructure.gateway.PythonHttpGateway;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PythonCapabilityController {
    private final PythonHttpGateway gateway;

    public PythonCapabilityController(PythonHttpGateway gateway) { this.gateway = gateway; }

    @RequestMapping({"/", "/assets/**", "/__build", "/docs", "/docs/**", "/openapi.json",
            "/health", "/file/**", "/document/**", "/skill/**", "/session/**", "/agent/**",
            "/execution/**", "/evaluation/**", "/release/**", "/harness/**", "/code-map", "/code-map/**",
            "/doc-asset/**", "/generated/**", "/console", "/console/**", "/favicon.ico"})
    public void forward(HttpServletRequest request, HttpServletResponse response) throws IOException {
        gateway.forward(request, response);
    }
}
