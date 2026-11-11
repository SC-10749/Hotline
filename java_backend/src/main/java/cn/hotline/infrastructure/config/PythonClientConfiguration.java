package cn.hotline.infrastructure.config;

import java.net.http.HttpClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PythonClientConfiguration {
    @Bean(destroyMethod = "close")
    HttpClient pythonHttpClient(PythonServiceProperties properties) {
        return HttpClient.newBuilder()
                // Uvicorn serves HTTP/1.1; avoid h2c upgrade on streamed request bodies.
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(properties.connectTimeout())
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Bean
    RestClient pythonRestClient(RestClient.Builder builder, HttpClient pythonHttpClient,
                               PythonServiceProperties properties) {
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(pythonHttpClient);
        factory.setReadTimeout(properties.readTimeout());
        return builder.requestFactory(factory).build();
    }
}
