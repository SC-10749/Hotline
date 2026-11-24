package cn.hotline.infrastructure.config;

import cn.hotline.trigger.http.SharedTokenFilter;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    public FilterRegistrationBean<SharedTokenFilter> sharedTokenFilter(SecurityProperties properties) {
        var registration = new FilterRegistrationBean<>(new SharedTokenFilter(properties.token()));
        registration.addUrlPatterns("/*");
        registration.setOrder(0);
        return registration;
    }
}
