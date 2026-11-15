package cn.hotline.trigger.listener;

import cn.hotline.infrastructure.config.MemoryAlarmProperties;
import cn.hutool.extra.spring.SpringUtil;
import com.alibaba.nacos.common.utils.MapUtil;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.Resource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Consumer;

/**
 * 内存使用监听告警器
 * @author coderzhn
 * @datetime 2026/11/15
 */
@Component
@EnableScheduling
public class MemoryAlarmListener {

    private static final Logger logger = LoggerFactory.getLogger(MemoryAlarmListener.class);

    @Resource
    private MemoryAlarmProperties memoryAlarmProperties;

    // 告警钩子函数，可以在需要的地方设置
    private static final Map<String, Consumer<MemoryUsage>> alarmHooks = new HashMap<>(4);

    //TODO:可以配置飞书机器人hook实现内存告警通知
    private static final String BOT_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/***";

    /**
     * 每20秒执行一次内存监控
     */
    @Scheduled(fixedRate = 20000)
    public void monitorMemory() {
        MemoryMXBean memoryMXBean = ManagementFactory.getMemoryMXBean();

        // 堆内存使用情况
        MemoryUsage heapMemoryUsage = memoryMXBean.getHeapMemoryUsage();

        // 非堆内存使用情况
        MemoryUsage nonHeapMemoryUsage = memoryMXBean.getNonHeapMemoryUsage();

        // 打印总体情况
        logger.info("=== 内存使用情况 ===");
        logger.info("堆内存: 已用={} MB, 提交={} MB, 最大={} MB",
                bytesToMB(heapMemoryUsage.getUsed()),
                bytesToMB(heapMemoryUsage.getCommitted()),
                bytesToMB(heapMemoryUsage.getMax()));

        logger.info("非堆内存: 已用={} MB, 提交={} MB, 最大={} MB",
                bytesToMB(nonHeapMemoryUsage.getUsed()),
                bytesToMB(nonHeapMemoryUsage.getCommitted()),
                bytesToMB(nonHeapMemoryUsage.getMax()));

        // 打印各内存池情况
        List<MemoryPoolMXBean> memoryPoolMXBeans = ManagementFactory.getMemoryPoolMXBeans();
        for (MemoryPoolMXBean memoryPoolMXBean : memoryPoolMXBeans) {
            MemoryUsage poolUsage = memoryPoolMXBean.getUsage();
            logger.info("内存池[{}]: 已用={} MB, 提交={} MB, 最大={} MB",
                    memoryPoolMXBean.getName(),
                    bytesToMB(poolUsage.getUsed()),
                    bytesToMB(poolUsage.getCommitted()),
                    bytesToMB(poolUsage.getMax()));
        }

        // 计算总内存使用量（堆 + 非堆）
        long totalUsedMemoryMB = bytesToMB(heapMemoryUsage.getUsed()) + bytesToMB(nonHeapMemoryUsage.getUsed());
        logger.info("总内存使用: {} MB, 告警阈值: {} MB", totalUsedMemoryMB, memoryAlarmProperties.getThreshold());

        // 检查是否超过阈值
        if (totalUsedMemoryMB > memoryAlarmProperties.getThreshold()) {
            logger.warn("内存使用超过告警阈值: 当前={} MB, 阈值={} MB", totalUsedMemoryMB, memoryAlarmProperties.getThreshold());
            // 触发告警钩子
            if (MapUtil.isNotEmpty(alarmHooks) && Objects.equals(Boolean.TRUE, memoryAlarmProperties.getEnabled())) {
                alarmHooks.forEach((name, hook) -> hook.accept(heapMemoryUsage));
            }
        }
    }

    /**
     * 字节转换为MB
     */
    private long bytesToMB(long bytes) {
        return bytes / (1024 * 1024);
    }

    @PostConstruct
    public void init() {
        alarmHooks.put("feishu", usage -> {
            String message = String.format("请查看内存情况: 当前used = %sMB, commited = %sMB", bytesToMB(usage.getUsed()), bytesToMB(usage.getCommitted()));
            String application = SpringUtil.getProperty("spring.application.name");
            if (application != null) {
                //TODO: 发送飞书消息
            }
        });
    }
}
