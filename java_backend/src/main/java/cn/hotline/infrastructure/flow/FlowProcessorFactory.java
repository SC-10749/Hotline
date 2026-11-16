package cn.hotline.infrastructure.flow;

import cn.hotline.domain.flow.FlowConfigurationException;
import cn.hotline.domain.flow.FlowItemProcessor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.context.ApplicationContext;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

/**
 * 处理器工厂：fmap 键 → 处理器实例，带缓存。
 * 对应 pandora TaskProcessorCache 的“按 fmap 索引缓存 + 反射实例化”；
 * 这里优先复用 Spring 容器中的 Bean（便于注入依赖），容器中不存在时才反射创建。
 */
public class FlowProcessorFactory {

    private static final Logger log = LoggerFactory.getLogger(FlowProcessorFactory.class);
    private static final int MAX_CACHED_PROCESSORS = 512;

    private final ApplicationContext applicationContext;
    private final ConcurrentMap<String, FlowItemProcessor> cache = new ConcurrentHashMap<>();

    public FlowProcessorFactory(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public FlowItemProcessor resolve(String fmapKey, String className) {
        FlowItemProcessor cached = cache.get(fmapKey);
        if (cached != null) {
            return cached;
        }
        if (!cache.containsKey(fmapKey) && cache.size() >= MAX_CACHED_PROCESSORS) {
            throw new FlowConfigurationException("处理器缓存超过上限 " + MAX_CACHED_PROCESSORS + "，拒绝任务 " + fmapKey);
        }
        return cache.computeIfAbsent(fmapKey, key -> create(fmapKey, className));
    }

    private FlowItemProcessor create(String fmapKey, String className) {
        Class<?> processorType;
        try {
            processorType = Class.forName(className);
        } catch (ClassNotFoundException exception) {
            throw new FlowConfigurationException("处理器类不存在：" + className + "（fmap 键 " + fmapKey + "）", exception);
        }
        if (!FlowItemProcessor.class.isAssignableFrom(processorType)) {
            throw new FlowConfigurationException("处理器未实现 FlowItemProcessor：" + className);
        }
        FlowItemProcessor fromContainer = lookupInContainer(processorType);
        if (fromContainer != null) {
            log.debug("复用 Spring 容器处理器 {}（fmap 键 {}）", className, fmapKey);
            return fromContainer;
        }
        try {
            FlowItemProcessor created = (FlowItemProcessor) processorType.getDeclaredConstructor().newInstance();
            log.debug("反射创建处理器 {}（fmap 键 {}）", className, fmapKey);
            return created;
        } catch (ReflectiveOperationException exception) {
            throw new FlowConfigurationException("处理器无法实例化：" + className, exception);
        }
    }

    private FlowItemProcessor lookupInContainer(Class<?> processorType) {
        try {
            if (applicationContext.getBeanNamesForType(processorType, true, false).length == 0) {
                return null;
            }
            return (FlowItemProcessor) applicationContext.getBean(processorType);
        } catch (NoUniqueBeanDefinitionException exception) {
            log.warn("处理器类型 {} 存在多个 Bean，改用反射创建", processorType.getName());
            return null;
        }
    }
}
