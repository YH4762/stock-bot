if has_data:
            # 1. 슬랙 전송
            send_slack("\n".join(msg_lines))
            
            # -----------------------------------------------------------
            # [수정됨] 2. 데이터 중복 방지 및 저장 로직
            # -----------------------------------------------------------
            save_allowed = True # 기본값: 저장 허용

            # 파일이 이미 존재하면 중복 검사
            if os.path.exists(FILE_NAME):
                try:
                    df_existing = pd.read_csv(FILE_NAME)
                    
                    # 중복 조건: 기업명 + 연도 + 분기가 모두 같으면 중복
                    # (save_row 딕셔너리에 해당 키가 있다고 가정)
                    check_condition = (
                        (df_existing['corp_name'] == corp_name) & 
                        (df_existing['year'] == save_row['year']) & 
                        (df_existing['quarter'] == save_row['quarter'])
                    )
                    
                    if check_condition.any():
                        save_allowed = False
                        print(f"   ⚠️ [중복 감지] {corp_name} {save_row['year']} {save_row['quarter']} 데이터가 이미 있습니다. (저장 건너뜀)")
                except Exception as e:
                    print(f"   ⚠️ 중복 검사 중 오류 발생 (덮어쓰기 진행): {e}")

            # 중복이 아닐 때만 저장 실행
            if save_allowed:
                df_new = pd.DataFrame([save_row])
                if os.path.exists(FILE_NAME):
                    df_new.to_csv(FILE_NAME, mode='a', header=False, index=False)
                else:
                    df_new.to_csv(FILE_NAME, index=False)
                print(f"   💾 {corp_name} 데이터 저장 완료")
            
            success_count += 1
            time.sleep(1) # 도배 방지

    except Exception as e:
        print(f"   ⚠️ {corp_name} 처리 중 에러: {e}")
        error_count += 1
