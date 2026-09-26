-- ============================================================
-- dify_platform_schema.sql — 경영시스템문서 플랫폼 통합 스키마 (2026-09-13 기준)
--
-- 이 파일은 로컬 PostgreSQL 16 테스트 DB(기존 base 스키마 + 06/08순 조직·책임과 권한
-- 마이그레이션 + 이번 회차 4순위 최종단계 "문서관리" 마이그레이션까지 전부 적용된 상태)에서
-- pg_dump --schema-only로 그대로 추출한 최신 스냅샷입니다. 총 34개 테이블.
--
-- 신규 설치 시: 이 파일 하나로 전체 스키마를 만들 수 있습니다(seed 데이터는 별도 —
-- dify_doc_type_seed.sql 등 프로젝트의 시드 스크립트를 이어서 실행하세요).
-- 기존 운영 DB(이미 데이터가 있는 Cloud SQL 등)에는 이 파일을 그대로 실행하지 말고,
-- scripts/10_migrate_doc_management.py처럼 컬럼 존재 여부를 확인하는 멱등 마이그레이션
-- 스크립트로 반영하세요.
-- ============================================================

--
-- PostgreSQL database dump
--


-- Dumped from database version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: application; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application (
    application_id bigint NOT NULL,
    company_id bigint,
    sample_name character varying(200),
    org_scale character varying(20),
    project_no character varying(120) NOT NULL,
    std_code_normalized character varying(4) NOT NULL,
    active_stds jsonb NOT NULL,
    sector_code character varying(10) NOT NULL,
    profile_id bigint,
    org_chart_id bigint,
    status character varying(20) DEFAULT 'in_progress'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    org_rr_status character varying(20) DEFAULT '미시작'::character varying NOT NULL,
    original_no smallint,
    CONSTRAINT application_check CHECK ((((company_id IS NOT NULL) AND (sample_name IS NULL)) OR ((company_id IS NULL) AND (sample_name IS NOT NULL))))
);


--
-- Name: application_application_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.application_application_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: application_application_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.application_application_id_seq OWNED BY public.application.application_id;


--
-- Name: company; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company (
    company_id bigint NOT NULL,
    company_name character varying(200) NOT NULL,
    biz_reg_no character varying(20),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: company_company_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_company_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_company_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_company_id_seq OWNED BY public.company.company_id;


--
-- Name: conversion_project; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversion_project (
    conversion_id bigint NOT NULL,
    application_id bigint NOT NULL,
    project_no character varying(120) NOT NULL,
    format character varying(10) NOT NULL,
    status character varying(20) DEFAULT 'requested'::character varying NOT NULL,
    storage_root_path character varying(500),
    requested_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone
);


--
-- Name: conversion_project_conversion_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversion_project_conversion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversion_project_conversion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversion_project_conversion_id_seq OWNED BY public.conversion_project.conversion_id;


--
-- Name: dept_master; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dept_master (
    dept_code character varying(20) NOT NULL,
    dept_name character varying(100) NOT NULL,
    category_code character varying(20) NOT NULL,
    category_name character varying(50) NOT NULL,
    category_seq integer NOT NULL,
    is_custom boolean DEFAULT false NOT NULL,
    relevant_std jsonb
);


--
-- Name: dept_responsibility; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dept_responsibility (
    resp_id bigint NOT NULL,
    role_id bigint NOT NULL,
    category character varying(10) NOT NULL,
    seq integer DEFAULT 0 NOT NULL,
    content text NOT NULL,
    authority_criteria character varying(300),
    related_step_id bigint,
    basis_doc character varying(300),
    required_competency character varying(300)
);


--
-- Name: dept_responsibility_resp_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dept_responsibility_resp_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dept_responsibility_resp_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dept_responsibility_resp_id_seq OWNED BY public.dept_responsibility.resp_id;


--
-- Name: doc_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.doc_type (
    doc_type_id bigint NOT NULL,
    doc_type_code character varying(30) NOT NULL,
    doc_type_name character varying(100) NOT NULL,
    category character varying(20) NOT NULL,
    applicable_std jsonb NOT NULL,
    applicable_label character varying(30),
    is_mandatory boolean DEFAULT true NOT NULL,
    clause_ref character varying(20),
    remark text,
    subcategory character varying(10),
    subcategory_group character varying(30),
    subcategory_letter character(1),
    display_code character varying(20),
    source_project_title character varying(120),
    source_original character varying(120),
    form_pattern_code character varying(30)
);


--
-- Name: doc_type_doc_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.doc_type_doc_type_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: doc_type_doc_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.doc_type_doc_type_id_seq OWNED BY public.doc_type.doc_type_id;


--
-- Name: document_content; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_content (
    content_id bigint NOT NULL,
    doc_id bigint NOT NULL,
    extracted_at timestamp with time zone DEFAULT now() NOT NULL,
    format character varying(10) DEFAULT 'hwp'::character varying NOT NULL,
    storage_path character varying(500)
);


--
-- Name: document_content_content_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_content_content_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_content_content_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_content_content_id_seq OWNED BY public.document_content.content_id;


--
-- Name: document_individual; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_individual (
    doc_id bigint NOT NULL,
    application_id bigint NOT NULL,
    conversion_project_id bigint,
    doc_type_id bigint NOT NULL,
    revision_no integer DEFAULT 1 NOT NULL,
    format character varying(10) NOT NULL,
    storage_path character varying(500),
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    form_seq_no character varying(20),
    CONSTRAINT document_individual_check CHECK ((((conversion_project_id IS NULL) AND ((format)::text = 'hwp'::text)) OR ((conversion_project_id IS NOT NULL) AND ((format)::text = ANY ((ARRAY['xlsx'::character varying, 'docx'::character varying])::text[])))))
);


--
-- Name: document_individual_doc_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_individual_doc_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_individual_doc_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_individual_doc_id_seq OWNED BY public.document_individual.doc_id;


--
-- Name: document_integrated; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_integrated (
    integrated_id bigint NOT NULL,
    application_id bigint NOT NULL,
    conversion_project_id bigint,
    revision_no integer DEFAULT 1 NOT NULL,
    format character varying(10) DEFAULT 'hwp'::character varying NOT NULL,
    bundle_scope character varying(10) DEFAULT 'core'::character varying NOT NULL,
    storage_path character varying(500),
    composed_doc_ids jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    CONSTRAINT document_integrated_bundle_scope_check CHECK (((bundle_scope)::text = ANY ((ARRAY['core'::character varying, 'guideline'::character varying])::text[]))),
    CONSTRAINT document_integrated_check CHECK ((((conversion_project_id IS NULL) AND ((format)::text = 'hwp'::text)) OR ((conversion_project_id IS NOT NULL) AND ((format)::text = ANY ((ARRAY['xlsx'::character varying, 'docx'::character varying])::text[])))))
);


--
-- Name: document_integrated_integrated_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_integrated_integrated_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_integrated_integrated_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_integrated_integrated_id_seq OWNED BY public.document_integrated.integrated_id;


--
-- Name: document_revision_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_revision_log (
    log_id bigint NOT NULL,
    doc_id bigint,
    integrated_id bigint,
    revision_no integer NOT NULL,
    change_note text,
    changed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: document_revision_log_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_revision_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_revision_log_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_revision_log_log_id_seq OWNED BY public.document_revision_log.log_id;


--
-- Name: form_field; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.form_field (
    field_id bigint NOT NULL,
    form_id bigint NOT NULL,
    field_name character varying(100) NOT NULL,
    field_type character varying(20) NOT NULL,
    seq integer DEFAULT 0 NOT NULL
);


--
-- Name: form_field_field_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.form_field_field_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: form_field_field_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.form_field_field_id_seq OWNED BY public.form_field.field_id;


--
-- Name: form_pattern; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.form_pattern (
    pattern_code character varying(30) NOT NULL,
    pattern_name character varying(100) NOT NULL,
    description text
);


--
-- Name: form_template; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.form_template (
    form_id bigint NOT NULL,
    application_id bigint NOT NULL,
    step_id bigint,
    form_name character varying(200) NOT NULL
);


--
-- Name: form_template_form_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.form_template_form_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: form_template_form_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.form_template_form_id_seq OWNED BY public.form_template.form_id;


--
-- Name: guideline_item; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.guideline_item (
    item_id bigint NOT NULL,
    application_id bigint NOT NULL,
    doc_type_id bigint NOT NULL,
    item_title character varying(200) NOT NULL,
    tech_standard text,
    work_method text,
    source_regulation character varying(200),
    content_source_type character varying(20) DEFAULT 'sample'::character varying NOT NULL,
    needs_review boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: guideline_item_item_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.guideline_item_item_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: guideline_item_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.guideline_item_item_id_seq OWNED BY public.guideline_item.item_id;


--
-- Name: hwp_render_job; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hwp_render_job (
    job_id bigint NOT NULL,
    doc_id bigint,
    integrated_id bigint,
    render_server character varying(20) DEFAULT 'windows'::character varying NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    request_payload jsonb,
    output_path character varying(500),
    error_msg text,
    requested_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT hwp_render_job_check CHECK (((doc_id IS NOT NULL) OR (integrated_id IS NOT NULL)))
);


--
-- Name: hwp_render_job_job_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.hwp_render_job_job_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: hwp_render_job_job_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.hwp_render_job_job_id_seq OWNED BY public.hwp_render_job.job_id;


--
-- Name: iaf_group; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iaf_group (
    iaf_num character varying(2) NOT NULL,
    name character varying(100) NOT NULL
);


--
-- Name: legacy_source_document; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.legacy_source_document (
    legacy_id bigint NOT NULL,
    file_name character varying(300) NOT NULL,
    uploaded_at timestamp with time zone DEFAULT now() NOT NULL,
    note text,
    application_id bigint
);


--
-- Name: legacy_source_document_legacy_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.legacy_source_document_legacy_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: legacy_source_document_legacy_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.legacy_source_document_legacy_id_seq OWNED BY public.legacy_source_document.legacy_id;


--
-- Name: legacy_split_mapping; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.legacy_split_mapping (
    mapping_id bigint NOT NULL,
    legacy_id bigint NOT NULL,
    doc_id bigint NOT NULL
);


--
-- Name: legacy_split_mapping_mapping_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.legacy_split_mapping_mapping_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: legacy_split_mapping_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.legacy_split_mapping_mapping_id_seq OWNED BY public.legacy_split_mapping.mapping_id;


--
-- Name: org_chart; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.org_chart (
    org_chart_id bigint NOT NULL,
    org_chart_name character varying(200) NOT NULL,
    industry_tag character varying(50),
    company_size_tag character varying(20),
    source_company_id bigint,
    is_template boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    application_id bigint
);


--
-- Name: org_chart_org_chart_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.org_chart_org_chart_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: org_chart_org_chart_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.org_chart_org_chart_id_seq OWNED BY public.org_chart.org_chart_id;


--
-- Name: org_chart_role; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.org_chart_role (
    role_id bigint NOT NULL,
    org_chart_id bigint NOT NULL,
    role_name character varying(100) NOT NULL,
    department character varying(100),
    parent_role_id bigint,
    seq integer DEFAULT 0 NOT NULL,
    dept_code character varying(20),
    mission text
);


--
-- Name: org_chart_role_role_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.org_chart_role_role_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: org_chart_role_role_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.org_chart_role_role_id_seq OWNED BY public.org_chart_role.role_id;


--
-- Name: org_rr_approval_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.org_rr_approval_log (
    log_id bigint NOT NULL,
    application_id bigint NOT NULL,
    rev_no integer NOT NULL,
    snapshot jsonb NOT NULL,
    approved_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: org_rr_approval_log_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.org_rr_approval_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: org_rr_approval_log_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.org_rr_approval_log_log_id_seq OWNED BY public.org_rr_approval_log.log_id;


--
-- Name: process_dependency; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.process_dependency (
    dependency_id bigint NOT NULL,
    from_step_id bigint NOT NULL,
    to_step_id bigint NOT NULL
);


--
-- Name: process_dependency_dependency_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.process_dependency_dependency_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: process_dependency_dependency_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.process_dependency_dependency_id_seq OWNED BY public.process_dependency.dependency_id;


--
-- Name: process_step; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.process_step (
    step_id bigint NOT NULL,
    application_id bigint NOT NULL,
    doc_type_id bigint NOT NULL,
    pdca_stage character varying(1) NOT NULL,
    stage_seq integer NOT NULL,
    step_name character varying(200) NOT NULL,
    clause_no character varying(10),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: process_step_activity; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.process_step_activity (
    activity_id bigint NOT NULL,
    step_id bigint NOT NULL,
    activity_desc text NOT NULL,
    seq integer DEFAULT 0 NOT NULL
);


--
-- Name: process_step_activity_activity_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.process_step_activity_activity_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: process_step_activity_activity_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.process_step_activity_activity_id_seq OWNED BY public.process_step_activity.activity_id;


--
-- Name: process_step_io; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.process_step_io (
    io_id bigint NOT NULL,
    step_id bigint NOT NULL,
    io_type character varying(10) NOT NULL,
    io_desc character varying(300) NOT NULL
);


--
-- Name: process_step_io_io_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.process_step_io_io_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: process_step_io_io_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.process_step_io_io_id_seq OWNED BY public.process_step_io.io_id;


--
-- Name: process_step_step_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.process_step_step_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: process_step_step_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.process_step_step_id_seq OWNED BY public.process_step.step_id;


--
-- Name: process_term_usage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.process_term_usage (
    usage_id bigint NOT NULL,
    step_id bigint NOT NULL,
    term_id bigint NOT NULL
);


--
-- Name: process_term_usage_usage_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.process_term_usage_usage_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: process_term_usage_usage_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.process_term_usage_usage_id_seq OWNED BY public.process_term_usage.usage_id;


--
-- Name: responsibility_matrix; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.responsibility_matrix (
    resp_id bigint NOT NULL,
    step_id bigint NOT NULL,
    role_id bigint NOT NULL,
    resp_type character varying(10) NOT NULL
);


--
-- Name: responsibility_matrix_resp_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.responsibility_matrix_resp_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: responsibility_matrix_resp_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.responsibility_matrix_resp_id_seq OWNED BY public.responsibility_matrix.resp_id;


--
-- Name: sample_doc_classification; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sample_doc_classification (
    classification_id bigint NOT NULL,
    analysis_id bigint,
    doc_title character varying(200) NOT NULL,
    doc_excerpt text,
    llm_category character varying(20),
    llm_reasoning text,
    reviewed boolean DEFAULT false NOT NULL,
    resulting_doc_type_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sample_doc_classification_classification_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sample_doc_classification_classification_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sample_doc_classification_classification_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sample_doc_classification_classification_id_seq OWNED BY public.sample_doc_classification.classification_id;


--
-- Name: sample_original; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sample_original (
    original_no smallint NOT NULL,
    original_name character varying(300) NOT NULL
);


--
-- Name: sample_original_original_no_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sample_original_original_no_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sample_original_original_no_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sample_original_original_no_seq OWNED BY public.sample_original.original_no;


--
-- Name: sample_project_analysis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sample_project_analysis (
    analysis_id bigint NOT NULL,
    source_file_name character varying(255) NOT NULL,
    excerpt_text text,
    candidate_profile_ids jsonb,
    matched_keywords jsonb,
    llm_sector_code character varying(10),
    llm_profile_seq smallint,
    llm_reasoning text,
    reviewed boolean DEFAULT false NOT NULL,
    resulting_profile_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sample_project_analysis_analysis_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sample_project_analysis_analysis_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sample_project_analysis_analysis_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sample_project_analysis_analysis_id_seq OWNED BY public.sample_project_analysis.analysis_id;


--
-- Name: sector_main; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sector_main (
    code character(1) NOT NULL,
    name character varying(50) NOT NULL
);


--
-- Name: sector_profile; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sector_profile (
    profile_id bigint NOT NULL,
    sector_code character varying(10) NOT NULL,
    profile_seq smallint NOT NULL,
    sector_main character(1) NOT NULL,
    iaf_num character varying(2) NOT NULL,
    sector_detail character(1) NOT NULL,
    sector_name character varying(200) NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    hazards jsonb DEFAULT '[]'::jsonb NOT NULL,
    env_aspects jsonb DEFAULT '[]'::jsonb NOT NULL,
    quality_chars jsonb DEFAULT '[]'::jsonb NOT NULL,
    key_laws_sh jsonb DEFAULT '[]'::jsonb NOT NULL,
    key_laws_env jsonb DEFAULT '[]'::jsonb NOT NULL,
    process_hints jsonb DEFAULT '[]'::jsonb NOT NULL,
    source_type character varying(20) DEFAULT 'iaf_csv'::character varying NOT NULL,
    created_by_company_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT sector_profile_profile_seq_check CHECK (((profile_seq >= 1) AND (profile_seq <= 99)))
);


--
-- Name: sector_profile_profile_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sector_profile_profile_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sector_profile_profile_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sector_profile_profile_id_seq OWNED BY public.sector_profile.profile_id;


--
-- Name: standard; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.standard (
    std_code character varying(4) NOT NULL,
    iso_num character varying(20) NOT NULL,
    title character varying(50) NOT NULL,
    prefix character varying(4) NOT NULL
);


--
-- Name: term_dictionary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.term_dictionary (
    term_id bigint NOT NULL,
    std_code character varying(4) NOT NULL,
    term character varying(100) NOT NULL,
    definition text NOT NULL,
    source_clause character varying(20)
);


--
-- Name: term_dictionary_term_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.term_dictionary_term_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: term_dictionary_term_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.term_dictionary_term_id_seq OWNED BY public.term_dictionary.term_id;


--
-- Name: application application_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application ALTER COLUMN application_id SET DEFAULT nextval('public.application_application_id_seq'::regclass);


--
-- Name: company company_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company ALTER COLUMN company_id SET DEFAULT nextval('public.company_company_id_seq'::regclass);


--
-- Name: conversion_project conversion_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversion_project ALTER COLUMN conversion_id SET DEFAULT nextval('public.conversion_project_conversion_id_seq'::regclass);


--
-- Name: dept_responsibility resp_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dept_responsibility ALTER COLUMN resp_id SET DEFAULT nextval('public.dept_responsibility_resp_id_seq'::regclass);


--
-- Name: doc_type doc_type_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_type ALTER COLUMN doc_type_id SET DEFAULT nextval('public.doc_type_doc_type_id_seq'::regclass);


--
-- Name: document_content content_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_content ALTER COLUMN content_id SET DEFAULT nextval('public.document_content_content_id_seq'::regclass);


--
-- Name: document_individual doc_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_individual ALTER COLUMN doc_id SET DEFAULT nextval('public.document_individual_doc_id_seq'::regclass);


--
-- Name: document_integrated integrated_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_integrated ALTER COLUMN integrated_id SET DEFAULT nextval('public.document_integrated_integrated_id_seq'::regclass);


--
-- Name: document_revision_log log_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_revision_log ALTER COLUMN log_id SET DEFAULT nextval('public.document_revision_log_log_id_seq'::regclass);


--
-- Name: form_field field_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_field ALTER COLUMN field_id SET DEFAULT nextval('public.form_field_field_id_seq'::regclass);


--
-- Name: form_template form_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_template ALTER COLUMN form_id SET DEFAULT nextval('public.form_template_form_id_seq'::regclass);


--
-- Name: guideline_item item_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.guideline_item ALTER COLUMN item_id SET DEFAULT nextval('public.guideline_item_item_id_seq'::regclass);


--
-- Name: hwp_render_job job_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hwp_render_job ALTER COLUMN job_id SET DEFAULT nextval('public.hwp_render_job_job_id_seq'::regclass);


--
-- Name: legacy_source_document legacy_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legacy_source_document ALTER COLUMN legacy_id SET DEFAULT nextval('public.legacy_source_document_legacy_id_seq'::regclass);


--
-- Name: legacy_split_mapping mapping_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legacy_split_mapping ALTER COLUMN mapping_id SET DEFAULT nextval('public.legacy_split_mapping_mapping_id_seq'::regclass);


--
-- Name: org_chart org_chart_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_chart ALTER COLUMN org_chart_id SET DEFAULT nextval('public.org_chart_org_chart_id_seq'::regclass);


--
-- Name: org_chart_role role_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_chart_role ALTER COLUMN role_id SET DEFAULT nextval('public.org_chart_role_role_id_seq'::regclass);


--
-- Name: org_rr_approval_log log_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_rr_approval_log ALTER COLUMN log_id SET DEFAULT nextval('public.org_rr_approval_log_log_id_seq'::regclass);


--
-- Name: process_dependency dependency_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_dependency ALTER COLUMN dependency_id SET DEFAULT nextval('public.process_dependency_dependency_id_seq'::regclass);


--
-- Name: process_step step_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step ALTER COLUMN step_id SET DEFAULT nextval('public.process_step_step_id_seq'::regclass);


--
-- Name: process_step_activity activity_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step_activity ALTER COLUMN activity_id SET DEFAULT nextval('public.process_step_activity_activity_id_seq'::regclass);


--
-- Name: process_step_io io_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step_io ALTER COLUMN io_id SET DEFAULT nextval('public.process_step_io_io_id_seq'::regclass);


--
-- Name: process_term_usage usage_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_term_usage ALTER COLUMN usage_id SET DEFAULT nextval('public.process_term_usage_usage_id_seq'::regclass);


--
-- Name: responsibility_matrix resp_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsibility_matrix ALTER COLUMN resp_id SET DEFAULT nextval('public.responsibility_matrix_resp_id_seq'::regclass);


--
-- Name: sample_doc_classification classification_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_doc_classification ALTER COLUMN classification_id SET DEFAULT nextval('public.sample_doc_classification_classification_id_seq'::regclass);


--
-- Name: sample_original original_no; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_original ALTER COLUMN original_no SET DEFAULT nextval('public.sample_original_original_no_seq'::regclass);


--
-- Name: sample_project_analysis analysis_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_project_analysis ALTER COLUMN analysis_id SET DEFAULT nextval('public.sample_project_analysis_analysis_id_seq'::regclass);


--
-- Name: sector_profile profile_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_profile ALTER COLUMN profile_id SET DEFAULT nextval('public.sector_profile_profile_id_seq'::regclass);


--
-- Name: term_dictionary term_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.term_dictionary ALTER COLUMN term_id SET DEFAULT nextval('public.term_dictionary_term_id_seq'::regclass);


--
-- Name: application application_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application
    ADD CONSTRAINT application_pkey PRIMARY KEY (application_id);


--
-- Name: application application_project_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application
    ADD CONSTRAINT application_project_no_key UNIQUE (project_no);


--
-- Name: company company_biz_reg_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company
    ADD CONSTRAINT company_biz_reg_no_key UNIQUE (biz_reg_no);


--
-- Name: company company_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company
    ADD CONSTRAINT company_pkey PRIMARY KEY (company_id);


--
-- Name: conversion_project conversion_project_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversion_project
    ADD CONSTRAINT conversion_project_pkey PRIMARY KEY (conversion_id);


--
-- Name: conversion_project conversion_project_project_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversion_project
    ADD CONSTRAINT conversion_project_project_no_key UNIQUE (project_no);


--
-- Name: dept_master dept_master_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dept_master
    ADD CONSTRAINT dept_master_pkey PRIMARY KEY (dept_code);


--
-- Name: dept_responsibility dept_responsibility_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dept_responsibility
    ADD CONSTRAINT dept_responsibility_pkey PRIMARY KEY (resp_id);


--
-- Name: doc_type doc_type_doc_type_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_type
    ADD CONSTRAINT doc_type_doc_type_code_key UNIQUE (doc_type_code);


--
-- Name: doc_type doc_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_type
    ADD CONSTRAINT doc_type_pkey PRIMARY KEY (doc_type_id);


--
-- Name: document_content document_content_doc_id_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_content
    ADD CONSTRAINT document_content_doc_id_uniq UNIQUE (doc_id);


--
-- Name: document_content document_content_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_content
    ADD CONSTRAINT document_content_pkey PRIMARY KEY (content_id);


--
-- Name: document_individual document_individual_app_doctype_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_individual
    ADD CONSTRAINT document_individual_app_doctype_uniq UNIQUE (application_id, doc_type_id);


--
-- Name: document_individual document_individual_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_individual
    ADD CONSTRAINT document_individual_pkey PRIMARY KEY (doc_id);


--
-- Name: document_integrated document_integrated_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_integrated
    ADD CONSTRAINT document_integrated_pkey PRIMARY KEY (integrated_id);


--
-- Name: document_revision_log document_revision_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_revision_log
    ADD CONSTRAINT document_revision_log_pkey PRIMARY KEY (log_id);


--
-- Name: form_field form_field_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_field
    ADD CONSTRAINT form_field_pkey PRIMARY KEY (field_id);


--
-- Name: form_pattern form_pattern_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_pattern
    ADD CONSTRAINT form_pattern_pkey PRIMARY KEY (pattern_code);


--
-- Name: form_template form_template_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_template
    ADD CONSTRAINT form_template_pkey PRIMARY KEY (form_id);


--
-- Name: guideline_item guideline_item_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.guideline_item
    ADD CONSTRAINT guideline_item_pkey PRIMARY KEY (item_id);


--
-- Name: hwp_render_job hwp_render_job_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hwp_render_job
    ADD CONSTRAINT hwp_render_job_pkey PRIMARY KEY (job_id);


--
-- Name: iaf_group iaf_group_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iaf_group
    ADD CONSTRAINT iaf_group_pkey PRIMARY KEY (iaf_num);


--
-- Name: legacy_source_document legacy_source_document_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legacy_source_document
    ADD CONSTRAINT legacy_source_document_pkey PRIMARY KEY (legacy_id);


--
-- Name: legacy_split_mapping legacy_split_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legacy_split_mapping
    ADD CONSTRAINT legacy_split_mapping_pkey PRIMARY KEY (mapping_id);


--
-- Name: org_chart org_chart_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_chart
    ADD CONSTRAINT org_chart_pkey PRIMARY KEY (org_chart_id);


--
-- Name: org_chart_role org_chart_role_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_chart_role
    ADD CONSTRAINT org_chart_role_pkey PRIMARY KEY (role_id);


--
-- Name: org_rr_approval_log org_rr_approval_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_rr_approval_log
    ADD CONSTRAINT org_rr_approval_log_pkey PRIMARY KEY (log_id);


--
-- Name: process_dependency process_dependency_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_dependency
    ADD CONSTRAINT process_dependency_pkey PRIMARY KEY (dependency_id);


--
-- Name: process_step_activity process_step_activity_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step_activity
    ADD CONSTRAINT process_step_activity_pkey PRIMARY KEY (activity_id);


--
-- Name: process_step_io process_step_io_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step_io
    ADD CONSTRAINT process_step_io_pkey PRIMARY KEY (io_id);


--
-- Name: process_step process_step_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step
    ADD CONSTRAINT process_step_pkey PRIMARY KEY (step_id);


--
-- Name: process_term_usage process_term_usage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_term_usage
    ADD CONSTRAINT process_term_usage_pkey PRIMARY KEY (usage_id);


--
-- Name: responsibility_matrix responsibility_matrix_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsibility_matrix
    ADD CONSTRAINT responsibility_matrix_pkey PRIMARY KEY (resp_id);


--
-- Name: sample_doc_classification sample_doc_classification_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_doc_classification
    ADD CONSTRAINT sample_doc_classification_pkey PRIMARY KEY (classification_id);


--
-- Name: sample_original sample_original_original_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_original
    ADD CONSTRAINT sample_original_original_name_key UNIQUE (original_name);


--
-- Name: sample_original sample_original_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_original
    ADD CONSTRAINT sample_original_pkey PRIMARY KEY (original_no);


--
-- Name: sample_project_analysis sample_project_analysis_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_project_analysis
    ADD CONSTRAINT sample_project_analysis_pkey PRIMARY KEY (analysis_id);


--
-- Name: sector_main sector_main_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_main
    ADD CONSTRAINT sector_main_pkey PRIMARY KEY (code);


--
-- Name: sector_profile sector_profile_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_profile
    ADD CONSTRAINT sector_profile_pkey PRIMARY KEY (profile_id);


--
-- Name: sector_profile sector_profile_sector_code_profile_seq_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_profile
    ADD CONSTRAINT sector_profile_sector_code_profile_seq_key UNIQUE (sector_code, profile_seq);


--
-- Name: standard standard_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.standard
    ADD CONSTRAINT standard_pkey PRIMARY KEY (std_code);


--
-- Name: term_dictionary term_dictionary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.term_dictionary
    ADD CONSTRAINT term_dictionary_pkey PRIMARY KEY (term_id);


--
-- Name: idx_conversion_project_app; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversion_project_app ON public.conversion_project USING btree (application_id);


--
-- Name: idx_hwp_render_job_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hwp_render_job_status ON public.hwp_render_job USING btree (status);


--
-- Name: idx_sector_profile_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sector_profile_code ON public.sector_profile USING btree (sector_code);


--
-- Name: application application_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application
    ADD CONSTRAINT application_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(company_id);


--
-- Name: application application_org_chart_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application
    ADD CONSTRAINT application_org_chart_id_fkey FOREIGN KEY (org_chart_id) REFERENCES public.org_chart(org_chart_id);


--
-- Name: application application_original_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application
    ADD CONSTRAINT application_original_no_fkey FOREIGN KEY (original_no) REFERENCES public.sample_original(original_no);


--
-- Name: application application_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application
    ADD CONSTRAINT application_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES public.sector_profile(profile_id);


--
-- Name: conversion_project conversion_project_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversion_project
    ADD CONSTRAINT conversion_project_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(application_id);


--
-- Name: dept_responsibility dept_responsibility_related_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dept_responsibility
    ADD CONSTRAINT dept_responsibility_related_step_id_fkey FOREIGN KEY (related_step_id) REFERENCES public.process_step(step_id);


--
-- Name: dept_responsibility dept_responsibility_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dept_responsibility
    ADD CONSTRAINT dept_responsibility_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.org_chart_role(role_id);


--
-- Name: doc_type doc_type_form_pattern_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_type
    ADD CONSTRAINT doc_type_form_pattern_code_fkey FOREIGN KEY (form_pattern_code) REFERENCES public.form_pattern(pattern_code);


--
-- Name: document_content document_content_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_content
    ADD CONSTRAINT document_content_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.document_individual(doc_id);


--
-- Name: document_individual document_individual_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_individual
    ADD CONSTRAINT document_individual_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(application_id);


--
-- Name: document_individual document_individual_conversion_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_individual
    ADD CONSTRAINT document_individual_conversion_project_id_fkey FOREIGN KEY (conversion_project_id) REFERENCES public.conversion_project(conversion_id);


--
-- Name: document_individual document_individual_doc_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_individual
    ADD CONSTRAINT document_individual_doc_type_id_fkey FOREIGN KEY (doc_type_id) REFERENCES public.doc_type(doc_type_id);


--
-- Name: document_integrated document_integrated_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_integrated
    ADD CONSTRAINT document_integrated_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(application_id);


--
-- Name: document_integrated document_integrated_conversion_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_integrated
    ADD CONSTRAINT document_integrated_conversion_project_id_fkey FOREIGN KEY (conversion_project_id) REFERENCES public.conversion_project(conversion_id);


--
-- Name: document_revision_log document_revision_log_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_revision_log
    ADD CONSTRAINT document_revision_log_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.document_individual(doc_id);


--
-- Name: document_revision_log document_revision_log_integrated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_revision_log
    ADD CONSTRAINT document_revision_log_integrated_id_fkey FOREIGN KEY (integrated_id) REFERENCES public.document_integrated(integrated_id);


--
-- Name: form_field form_field_form_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_field
    ADD CONSTRAINT form_field_form_id_fkey FOREIGN KEY (form_id) REFERENCES public.form_template(form_id);


--
-- Name: form_template form_template_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_template
    ADD CONSTRAINT form_template_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(application_id);


--
-- Name: form_template form_template_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_template
    ADD CONSTRAINT form_template_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.process_step(step_id);


--
-- Name: guideline_item guideline_item_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.guideline_item
    ADD CONSTRAINT guideline_item_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(application_id);


--
-- Name: guideline_item guideline_item_doc_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.guideline_item
    ADD CONSTRAINT guideline_item_doc_type_id_fkey FOREIGN KEY (doc_type_id) REFERENCES public.doc_type(doc_type_id);


--
-- Name: hwp_render_job hwp_render_job_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hwp_render_job
    ADD CONSTRAINT hwp_render_job_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.document_individual(doc_id);


--
-- Name: hwp_render_job hwp_render_job_integrated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hwp_render_job
    ADD CONSTRAINT hwp_render_job_integrated_id_fkey FOREIGN KEY (integrated_id) REFERENCES public.document_integrated(integrated_id);


--
-- Name: legacy_source_document legacy_source_document_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legacy_source_document
    ADD CONSTRAINT legacy_source_document_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(application_id);


--
-- Name: legacy_split_mapping legacy_split_mapping_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legacy_split_mapping
    ADD CONSTRAINT legacy_split_mapping_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.document_individual(doc_id);


--
-- Name: legacy_split_mapping legacy_split_mapping_legacy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legacy_split_mapping
    ADD CONSTRAINT legacy_split_mapping_legacy_id_fkey FOREIGN KEY (legacy_id) REFERENCES public.legacy_source_document(legacy_id);


--
-- Name: org_chart org_chart_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_chart
    ADD CONSTRAINT org_chart_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(application_id);


--
-- Name: org_chart_role org_chart_role_dept_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_chart_role
    ADD CONSTRAINT org_chart_role_dept_code_fkey FOREIGN KEY (dept_code) REFERENCES public.dept_master(dept_code);


--
-- Name: org_chart_role org_chart_role_org_chart_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_chart_role
    ADD CONSTRAINT org_chart_role_org_chart_id_fkey FOREIGN KEY (org_chart_id) REFERENCES public.org_chart(org_chart_id);


--
-- Name: org_chart_role org_chart_role_parent_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_chart_role
    ADD CONSTRAINT org_chart_role_parent_role_id_fkey FOREIGN KEY (parent_role_id) REFERENCES public.org_chart_role(role_id);


--
-- Name: org_chart org_chart_source_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_chart
    ADD CONSTRAINT org_chart_source_company_id_fkey FOREIGN KEY (source_company_id) REFERENCES public.company(company_id);


--
-- Name: org_rr_approval_log org_rr_approval_log_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.org_rr_approval_log
    ADD CONSTRAINT org_rr_approval_log_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(application_id);


--
-- Name: process_dependency process_dependency_from_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_dependency
    ADD CONSTRAINT process_dependency_from_step_id_fkey FOREIGN KEY (from_step_id) REFERENCES public.process_step(step_id);


--
-- Name: process_dependency process_dependency_to_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_dependency
    ADD CONSTRAINT process_dependency_to_step_id_fkey FOREIGN KEY (to_step_id) REFERENCES public.process_step(step_id);


--
-- Name: process_step_activity process_step_activity_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step_activity
    ADD CONSTRAINT process_step_activity_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.process_step(step_id);


--
-- Name: process_step process_step_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step
    ADD CONSTRAINT process_step_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.application(application_id);


--
-- Name: process_step process_step_doc_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step
    ADD CONSTRAINT process_step_doc_type_id_fkey FOREIGN KEY (doc_type_id) REFERENCES public.doc_type(doc_type_id);


--
-- Name: process_step_io process_step_io_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_step_io
    ADD CONSTRAINT process_step_io_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.process_step(step_id);


--
-- Name: process_term_usage process_term_usage_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_term_usage
    ADD CONSTRAINT process_term_usage_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.process_step(step_id);


--
-- Name: process_term_usage process_term_usage_term_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.process_term_usage
    ADD CONSTRAINT process_term_usage_term_id_fkey FOREIGN KEY (term_id) REFERENCES public.term_dictionary(term_id);


--
-- Name: responsibility_matrix responsibility_matrix_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsibility_matrix
    ADD CONSTRAINT responsibility_matrix_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.org_chart_role(role_id);


--
-- Name: responsibility_matrix responsibility_matrix_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.responsibility_matrix
    ADD CONSTRAINT responsibility_matrix_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.process_step(step_id);


--
-- Name: sample_doc_classification sample_doc_classification_analysis_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_doc_classification
    ADD CONSTRAINT sample_doc_classification_analysis_id_fkey FOREIGN KEY (analysis_id) REFERENCES public.sample_project_analysis(analysis_id);


--
-- Name: sample_doc_classification sample_doc_classification_resulting_doc_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_doc_classification
    ADD CONSTRAINT sample_doc_classification_resulting_doc_type_id_fkey FOREIGN KEY (resulting_doc_type_id) REFERENCES public.doc_type(doc_type_id);


--
-- Name: sample_project_analysis sample_project_analysis_resulting_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sample_project_analysis
    ADD CONSTRAINT sample_project_analysis_resulting_profile_id_fkey FOREIGN KEY (resulting_profile_id) REFERENCES public.sector_profile(profile_id);


--
-- Name: sector_profile sector_profile_created_by_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_profile
    ADD CONSTRAINT sector_profile_created_by_company_id_fkey FOREIGN KEY (created_by_company_id) REFERENCES public.company(company_id);


--
-- Name: sector_profile sector_profile_iaf_num_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_profile
    ADD CONSTRAINT sector_profile_iaf_num_fkey FOREIGN KEY (iaf_num) REFERENCES public.iaf_group(iaf_num);


--
-- Name: sector_profile sector_profile_sector_main_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sector_profile
    ADD CONSTRAINT sector_profile_sector_main_fkey FOREIGN KEY (sector_main) REFERENCES public.sector_main(code);


--
-- PostgreSQL database dump complete
--


