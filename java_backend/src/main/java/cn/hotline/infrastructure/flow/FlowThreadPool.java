package cn.hotline.infrastructure.flow;

import cn.hotline.infrastructure.config.FlowProperties;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 流程并行任务线程池。对应 pandora-search-music 的 Abtest-task-pool：
 * SynchronousQueue 直接交接、核心线程保活、keepAlive 回收。
 * pandora 对超过 maxSize 的任务直接拒绝（任务失败）；这里改为回退到调用线程
 * 执行（CallerRuns 背压），避免并行分支被静默丢弃——组内任务失败会中断场景，
 * 而丢弃任务会造成等待方永久挂起。池关闭时仍抛 RejectedExecutionException，
 * 防止关闭窗口内静默吞掉任务。
 */
public class FlowThreadPool {

    private final ThreadPoolExecutor executor;

    public FlowThreadPool(FlowProperties.Pool pool) {
        this.executor = new ThreadPoolExecutor(
                pool.coreSize(),
                pool.maxSize(),
                pool.keepAlive().toMillis(),
                TimeUnit.MILLISECONDS,
                new SynchronousQueue<>(),
                new FlowThreadFactory(),
                (task, rejectedExecutor) -> {
                    if (rejectedExecutor.isShutdown()) {
                        throw new RejectedExecutionException("流程线程池已关闭");
                    }
                    task.run();
                });
    }

    public ExecutorService executor() {
        return executor;
    }

    public void close() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException exception) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    private static final class FlowThreadFactory implements ThreadFactory {

        private final AtomicInteger sequence = new AtomicInteger(1);

        @Override
        public Thread newThread(Runnable runnable) {
            return new Thread(runnable, "hotline-flow-" + sequence.getAndIncrement());
        }
    }
}
