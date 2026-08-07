package com.omecca.omeccabackend.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.sql.DataSource;
import java.sql.Connection;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/health")
public class HealthController {

    private final DataSource dataSource;

    public HealthController(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @GetMapping
    public Map<String, Object> health() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", "UP");
        body.put("service", "b_gateway");

        try (Connection connection = dataSource.getConnection()) {
            body.put("db", connection.isValid(2) ? "UP" : "DOWN");
            body.put("dbProduct", connection.getMetaData().getDatabaseProductName());
        } catch (Exception e) {
            body.put("status", "DOWN");
            body.put("db", "DOWN");
            body.put("error", e.getMessage());
        }
        return body;
    }
}
