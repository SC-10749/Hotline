package cn.hotline.infrastructure.config;

import cn.hotline.application.flow.FlowEngine;
import cn.hotline.infrastructure.flow.FlowProcessorFactory;
import cn.hotline.infrastructure.flow.FlowSceneRegistry;
import cn.hotline.infrastructure.flow.FlowThreadPool;
import cn.hotline.infrastructure.flow.FunctionMappings;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.DefaultResourceLoader;

/** 流程编排装配：funcmap、处理器工厂、场景注册表、线程池与引擎。 */
@Configuration
public class FlowConfiguration {

    @Bean
    public FunctionMappings flowFunctionMappings(FlowProperties properties) {
        return FunctionMappings.load(new DefaultResourceLoader().getResource(properties.funcmapsLocation()));
    }

    @Bean
    public FlowProcessorFactory flowProcessorFactory(ApplicationContext applicationContext) {
        return new FlowProcessorFactory(applicationContext);
    }

    @Bean
    public FlowSceneRegistry flowSceneRegistry(FlowProperties properties,
                                               FunctionMappings flowFunctionMappings,
                                               FlowProcessorFactory flowProcessorFactory,
                                               ObjectMapper objectMapper) {
        return new FlowSceneRegistry(new DefaultResourceLoader().getResource(properties.scenesLocation()),
                flowFunctionMappings, flowProcessorFactory, objectMapper);
    }

    @Bean(destroyMethod = "close")
    public FlowThreadPool flowThreadPool(FlowProperties properties) {
        return new FlowThreadPool(properties.pool());
    }

    @Bean
    public FlowEngine flowEngine(FlowSceneRegistry flowSceneRegistry, FlowThreadPool flowThreadPool) {
        return new FlowEngine(flowSceneRegistry, flowThreadPool);
    }
}
