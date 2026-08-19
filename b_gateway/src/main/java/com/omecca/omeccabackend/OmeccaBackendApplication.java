package com.omecca.omeccabackend;

import io.github.cdimascio.dotenv.Dotenv;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OmeccaBackendApplication {

    public static void main(String[] args) {
        // b_gateway/ 폴더(프로젝트 실행 위치)에 .env 파일이 있으면 자동으로 읽어서
        // System property로 등록한다 - GATEWAY_API_KEY, JWT_SECRET, DB_USERNAME,
        // DB_PASSWORD를 팀원이 매번 export($env:)로 직접 등록하지 않아도 되게 하기 위함.
        // .env 파일이 없어도(ignoreIfMissing) 에러 없이 그냥 넘어가고, 이 경우 기존처럼
        // OS 환경변수나 application.properties에 직접 넣은 값을 그대로 쓴다.
        //
        // 주의: SpringApplication.run()보다 반드시 먼저 실행돼야 한다 - Spring이
        // application.yml의 ${GATEWAY_API_KEY} 같은 플레이스홀더를 해석하는 시점에
        // System property도 함께 확인하기 때문에, 이 로딩이 늦으면 적용 안 된다.
        Dotenv dotenv = Dotenv.configure().ignoreIfMissing().load();
        dotenv.entries().forEach(entry -> {
            if (System.getProperty(entry.getKey()) == null && System.getenv(entry.getKey()) == null) {
                System.setProperty(entry.getKey(), entry.getValue());
            }
        });

        SpringApplication.run(OmeccaBackendApplication.class, args);
    }
}
