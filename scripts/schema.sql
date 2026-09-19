-- PortPulse MySQL Database Schema
-- Run this script in phpMyAdmin or MySQL client to initialize the database structure.

CREATE DATABASE IF NOT EXISTS `portpulse` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `portpulse`;

CREATE TABLE IF NOT EXISTS `prediction_log` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `vessel_id` VARCHAR(20),
    `window_day` INT,
    `vessel_count` INT,
    `incoming_teu` INT,
    `total_capacity_teu` INT,
    `utilization_ratio` FLOAT,
    `predicted_risk_level` VARCHAR(10),
    `predicted_wait_hours` FLOAT,
    `actual_wait_hours` FLOAT DEFAULT NULL,
    `actual_risk_level` VARCHAR(10) DEFAULT NULL,
    `model_version` VARCHAR(20),
    `origin_lat` FLOAT DEFAULT NULL,
    `origin_lon` FLOAT DEFAULT NULL,
    `origin_port` VARCHAR(128) DEFAULT NULL,
    `weather_delay_hours` FLOAT DEFAULT NULL,
    `weather_severity` VARCHAR(20) DEFAULT NULL,
    `predicted_demurrage_cost_usd` FLOAT DEFAULT NULL,
    `predicted_moves_per_hour` FLOAT DEFAULT NULL,
    `is_anomalous` TINYINT(1) DEFAULT NULL,
    `ml_allocation_used` TINYINT(1) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
