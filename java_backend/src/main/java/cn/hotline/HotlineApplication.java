package cn.hotline;

import cn.hotline.infrastructure.config.AdmissionProperties;
import cn.hotline.infrastructure.config.FlowProperties;
import cn.hotline.infrastructure.config.PythonServiceProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties({PythonServiceProperties.class, FlowProperties.class, AdmissionProperties.class})
public class HotlineApplication {
    public static void main(String[] args) {
        SpringApplication.run(HotlineApplication.class, args);
    }
}
