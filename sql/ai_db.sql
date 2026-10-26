/*
 Navicat Premium Dump SQL

 Source Server         : 127.0.0.1-localhost
 Source Server Type    : MySQL
 Source Server Version : 80041 (8.0.41)
 Source Host           : localhost:3306
 Source Schema         : dodo

 Target Server Type    : MySQL
 Target Server Version : 80041 (8.0.41)
 File Encoding         : 65001

 Date: 08/03/2026 18:52:49
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for ai_file_info
-- ----------------------------
DROP TABLE IF EXISTS `ai_file_info`;
CREATE TABLE `ai_file_info`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `file_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文件唯一标识',
  `file_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '原始文件名',
  `file_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件类型（pdf/doc/docx/txt/png/jpg等）',
  `file_size` bigint NULL DEFAULT NULL COMMENT '文件大小（字节）',
  `minio_path` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'MinIO中的存储路径',
  `extracted_text` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '解析后的纯文本内容',
  `created_at` datetime NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `conversation_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '会话ID（可选，用于关联特定会话）',
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT 'PENDING' COMMENT '文件状态：PENDING/PROCESSING/SUCCESS/FAILED',
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `embed` tinyint NULL DEFAULT NULL COMMENT '是否向量化',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_file_id`(`file_id` ASC) USING BTREE,
  INDEX `idx_conversation_id`(`conversation_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2029891708835364866 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '文件元数据表，存储文件基本信息和解析后的内容' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ai_ppt_inst
-- ----------------------------
DROP TABLE IF EXISTS `ai_ppt_inst`;
CREATE TABLE `ai_ppt_inst`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '实例ID',
  `conversation_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '会话ID',
  `template_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '选择的模板code',
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'INIT' COMMENT '状态',
  `query` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '用户原始需求',
  `requirement` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '需求澄清',
  `search_info` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '搜索信息',
  `outline` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '大纲',
  `ppt_schema` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT 'AI生成的PPT规划JSON',
  `file_url` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '生成的PPT文件URL',
  `error_msg` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '失败原因',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_conversation_id`(`conversation_id` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_template_code`(`template_code` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2030251353580011522 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'AI PPT生成实例表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for ai_ppt_template
-- ----------------------------
DROP TABLE IF EXISTS `ai_ppt_template`;
CREATE TABLE `ai_ppt_template`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '模板ID',
  `template_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '模板唯一编码',
  `template_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '模板名称',
  `template_desc` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '模板说明',
  `template_schema` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '模板结构JSON',
  `file_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'PPT模板文件路径',
  `style_tags` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '风格标签：科技,商务,简约',
  `slide_count` int NULL DEFAULT NULL COMMENT '模板页数',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `template_code`(`template_code` ASC) USING BTREE,
  INDEX `idx_template_code`(`template_code` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'AI PPT模板表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for ai_session
-- ----------------------------
DROP TABLE IF EXISTS `ai_session`;
CREATE TABLE `ai_session`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `session_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '会话ID',
  `question` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '用户问题',
  `answer` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT 'AI回复',
  `tools` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '涉及的执行工具名称（逗号分隔）',
  `first_response_time` bigint NULL DEFAULT NULL COMMENT '首次响应时间（毫秒）',
  `total_response_time` bigint NULL DEFAULT NULL COMMENT '整体回复时间（毫秒）',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `reference` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '参考链接',
  `agent_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '智能体类型',
  `thinking` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '思考过程',
  `fileid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '文件id',
  `recommend` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '推荐问题',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_session_id`(`session_id` ASC) USING BTREE COMMENT '会话ID索引',
  INDEX `idx_create_time`(`create_time` ASC) USING BTREE COMMENT '创建时间索引'
) ENGINE = InnoDB AUTO_INCREMENT = 2030594695312510979 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '存储智能体与用户的对话历史，支持会话隔离和记忆功能' ROW_FORMAT = DYNAMIC;

SET FOREIGN_KEY_CHECKS = 1;

INSERT INTO `dodo`.`ai_ppt_template` (`id`, `template_code`, `template_name`, `template_desc`, `template_schema`, `file_path`, `style_tags`, `slide_count`, `create_time`) VALUES (1, 'ai', 'AI科技风PPT', '适用于AI、人工智能、科技风等场景的PPT', '{\r\n  \"slides\": [\r\n    {\r\n      \"pageType\": \"COVER\",\r\n      \"pageDesc\": \"封面页\",\r\n      \"pageIndex\": 1,\r\n      \"data\": {\r\n        \"title\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"大标题\",\r\n          \"fontLimit\": 7\r\n        },\r\n        \"description\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"一句话描述\",\r\n          \"fontLimit\": 30         \r\n        },\r\n        \"author\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"作者姓名\",\r\n          \"fontLimit\": 10\r\n        }\r\n      }\r\n    },\r\n\r\n    {\r\n      \"pageType\": \"CATALOG\",\r\n      \"pageDesc\": \"目录页\",\r\n      \"pageIndex\": 2,\r\n      \"data\": {\r\n        \"catalog1\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"目录1\",\r\n          \"fontLimit\": 9\r\n        },\r\n        \"catalog2\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"目录2\",\r\n          \"fontLimit\": 9\r\n        },\r\n        \"catalog3\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"目录3\",\r\n          \"fontLimit\": 9\r\n        }\r\n      }\r\n    },\r\n\r\n    {\r\n      \"pageType\": \"COMPARE\",\r\n      \"pageDesc\": \"内容页，用于2者对比\",\r\n      \"pageIndex\": 3,\r\n      \"data\": {\r\n        \"title\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"大标题\",\r\n          \"fontLimit\": 9\r\n        },\r\n        \"content1\": {\r\n	      \"type\":\"text\",\r\n          \"content\": \"对比项1内容\",\r\n          \"fontLimit\": 60\r\n        },\r\n        \"content2\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"对比项2内容\",\r\n          \"fontLimit\": 60\r\n        }\r\n      }\r\n    },\r\n\r\n    {\r\n      \"pageType\": \"CONTENT\",\r\n      \"pageDesc\": \"内容页\",\r\n      \"pageIndex\": 4,\r\n      \"data\": {\r\n        \"title\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"大标题\",\r\n          \"fontLimit\": 9\r\n        },\r\n        \"subTitle\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"子标题\",\r\n          \"fontLimit\": 4\r\n        },\r\n        \"content\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"内容描述\",\r\n          \"fontLimit\": 55\r\n        },\r\n        \"image\": {\r\n		  \"type\":\"image\",\r\n          \"content\": \"根据需求生成配图\",\r\n          \"url\": \"图片URL地址\"\r\n        }\r\n      }\r\n    },\r\n\r\n    {\r\n      \"pageType\": \"END\",\r\n      \"pageDesc\": \"结束页\",\r\n      \"pageIndex\": 5,\r\n      \"data\": {\r\n        \"title\": {\r\n		  \"type\":\"text\",\r\n          \"content\": \"结束页大标题\",\r\n          \"fontLimit\": 5\r\n        }\r\n      }\r\n    }\r\n  ]\r\n}', 'C:\\Users\\Lenovo\\Desktop\\ppt-template\\ai.pptx', '科技、AI、人工智能', 5, '2026-02-23 14:53:15');

