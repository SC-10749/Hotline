package cn.hotline.infrastructure.config;

import com.alibaba.fastjson2.JSON;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Slf4j
@Data
@Component
public class MemoryAlarmProperties implements InitializingBean {

    /**
     * enabled
     */
    private Boolean enabled = true;

    /**
     * 阈值
     */
    private Integer threshold = 24576;

    @Override
    public void afterPropertiesSet() {
        log.info("memory alarm 配置:{}", JSON.toJSONString(this));
    }
}
