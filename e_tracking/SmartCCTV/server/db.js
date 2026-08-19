/**
 * db.js
 * ------------------------------------------------------------
 * PostgreSQL + PostGIS 연결 및 이동 경로(trajectory) 저장/조회.
 *
 * 이 DB는 b_gateway가 쓰는 MySQL과 완전히 별개다 - 이 모듈(e_tracking)만
 * 쓰는 전용 저장소다. MySQL 쪽 스키마/코드는 전혀 건드리지 않는다.
 *
 * 연결 실패해도 서버 전체가 죽지 않게 처리한다 - PostGIS가 아직 준비 안 됐어도
 * WebSocket 실시간 표시는 그대로 동작해야 하기 때문 (지도 기능이 저장 기능에
 * 종속되면 안 됨).
 */

const { Pool } = require("pg");

const pool = new Pool({
  host: process.env.PGHOST || "localhost",
  port: process.env.PGPORT || 5432,
  user: process.env.PGUSER || "postgres",
  password: process.env.PGPASSWORD || "",
  database: process.env.PGDATABASE || "omecca_gis",
});

let ready = false;

async function init() {
  try {
    await pool.query("CREATE EXTENSION IF NOT EXISTS postgis;");
    await pool.query(`
      CREATE TABLE IF NOT EXISTS trajectory (
        id                BIGSERIAL PRIMARY KEY,
        global_vehicle_id VARCHAR(100) NOT NULL,
        source_type       VARCHAR(10)  NOT NULL,
        source_id         VARCHAR(50)  NOT NULL,
        event_type        VARCHAR(50),
        location_name     VARCHAR(200),
        reason            TEXT,
        geom              geometry(Point, 4326) NOT NULL,
        recorded_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
      );
    `);
    await pool.query(`
      CREATE INDEX IF NOT EXISTS idx_trajectory_vehicle_time
        ON trajectory (global_vehicle_id, recorded_at);
    `);
    await pool.query(`
      CREATE INDEX IF NOT EXISTS idx_trajectory_geom
        ON trajectory USING GIST (geom);
    `);
    ready = true;
    console.log("[PostGIS] 연결 및 테이블 준비 완료");
  } catch (err) {
    ready = false;
    console.warn("[PostGIS] 연결 실패 - 경로 저장 없이 실시간 표시만 동작합니다:", err.message);
  }
}

async function saveEvent(payload) {
  if (!ready) return false;
  const globalId = payload.global_vehicle_id || `${payload.source_id}-${payload.track_id ?? "unknown"}`;
  try {
    await pool.query(
      `INSERT INTO trajectory
         (global_vehicle_id, source_type, source_id, event_type, location_name, reason, geom, recorded_at)
       VALUES ($1, $2, $3, $4, $5, $6, ST_SetSRID(ST_MakePoint($7, $8), 4326), to_timestamp($9))`,
      [
        globalId,
        payload.source_type,
        payload.source_id,
        payload.event_type || null,
        payload.location_name || null,
        payload.reason || null,
        payload.longitude,
        payload.latitude,
        payload.timestamp || Date.now() / 1000,
      ]
    );
    return true;
  } catch (err) {
    console.warn("[PostGIS] 이벤트 저장 실패:", err.message);
    return false;
  }
}

async function getTrajectory(globalVehicleId, limit = 500) {
  if (!ready) return [];
  const { rows } = await pool.query(
    `SELECT global_vehicle_id, source_type, source_id, event_type, location_name, reason,
            ST_Y(geom) AS latitude, ST_X(geom) AS longitude, recorded_at
       FROM trajectory
      WHERE global_vehicle_id = $1
      ORDER BY recorded_at ASC
      LIMIT $2`,
    [globalVehicleId, limit]
  );
  return rows;
}

async function listRecentVehicles(minutes = 60) {
  if (!ready) return [];
  const { rows } = await pool.query(
    `SELECT global_vehicle_id, MAX(recorded_at) AS last_seen
       FROM trajectory
      WHERE recorded_at > now() - ($1 || ' minutes')::interval
      GROUP BY global_vehicle_id
      ORDER BY last_seen DESC`,
    [minutes]
  );
  return rows;
}

module.exports = { init, saveEvent, getTrajectory, listRecentVehicles, isReady: () => ready };