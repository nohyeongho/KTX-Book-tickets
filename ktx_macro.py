# -*- coding: utf-8 -*-
"""
KTX 취소표 실시간 자동 예약 및 알림 프로그램 (하단 예매 버튼 클릭 강화 버전)

[개선 내역]
1. 하단 [예매] 버튼 클릭 강화:
   - <button> 및 <a> 태그 모두 지원
   - 공백 및 자식 태그(<span> 등) 포함 시에도 완벽 탐색
   - 화면 하단 고정 바 내부의 파란색 [예매] 버튼을 최우선 정밀 타겟팅
2. 좌석 클릭 후 하단 바 활성화 대기 시간 부여
3. 순수 F5(driver.refresh()) 기반의 안전한 새로고침 유지
4. 단축키(p: 일시정지, Enter: 재개, q: 종료) 지원
"""

import time
import random
import re
import sys

try:
    import winsound
except ImportError:
    winsound = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
)

import config


def create_browser():
    """
    크롬 브라우저를 생성합니다.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    return driver


def play_alarm():
    """
    예약 성공 시 비프음을 울립니다.
    """
    if config.ENABLE_BEEP_SOUND and winsound:
        print("\n📢 [알림] 좌석이 확보되었습니다! 비프음을 울립니다.")
        for _ in range(config.BEEP_REPEAT_COUNT):
            winsound.Beep(1500, 400)
            time.sleep(0.1)


def is_train_list_loaded(driver):
    """
    열차 목록이 화면에 정상 렌더링되었는지 확인합니다.
    """
    try:
        train_rows = driver.find_elements(By.CSS_SELECTOR, "div.tck_inner, div.tck_etc_use")
        return len(train_rows) > 0
    except:
        return False


def click_bottom_reserve_button(driver):
    """
    [핵심 개선 함수]
    좌석 선택 후 화면 맨 아래 나타나는 파란색 [예매] 버튼을 확실하게 찾아 클릭합니다.
    - <button>, <a> 태그 모두 탐색
    - 상단 메뉴의 '승차권 예매'가 아닌, 하단 바의 순수 '예매' 버튼을 정밀 타겟팅
    """
    # 좌석 선택 후 하단 바가 활성화(애니메이션)될 수 있도록 0.5초 대기
    time.sleep(0.5)

    # 1순위: 텍스트가 정확히 '예매'인 button 또는 a 태그 (공백 제거 normalize-space)
    exact_reserve_btns = driver.find_elements(
        By.XPATH,
        "//button[normalize-space()='예매'] | //a[normalize-space()='예매'] | "
        "//button[normalize-space()='예매하기'] | //a[normalize-space()='예매하기']"
    )

    if exact_reserve_btns:
        for btn in reversed(exact_reserve_btns):
            try:
                # 화면에 실제로 보이는 버튼 클릭
                if btn.is_displayed():
                    print(f"👉 [하단 예매 버튼 클릭!] 태그=<{btn.tag_name}> 클래스='{btn.get_attribute('class')}'")
                    driver.execute_script("arguments[0].click();", btn)
                    return True
            except:
                continue

    # 2순위: span 태그 등으로 감싸져 있는 경우 (예: <a><span>예매</span></a>)
    span_reserve = driver.find_elements(
        By.XPATH,
        "//span[normalize-space()='예매']/ancestor::a[1] | //span[normalize-space()='예매']/ancestor::button[1]"
    )
    if span_reserve:
        for btn in reversed(span_reserve):
            try:
                if btn.is_displayed():
                    print(f"👉 [하단 예매 감싸기 버튼 클릭!] 태그=<{btn.tag_name}>")
                    driver.execute_script("arguments[0].click();", btn)
                    return True
            except:
                continue

    # 3순위: '예매' 텍스트를 포함하고 클래스에 btn이나 blue가 들어간 요소
    broad_btns = driver.find_elements(
        By.XPATH,
        "//*[(self::button or self::a) and contains(., '예매') and not(contains(., '승차권'))]"
    )
    if broad_btns:
        for btn in reversed(broad_btns):
            try:
                if btn.is_displayed():
                    print(f"👉 [대체 예매 버튼 클릭!] 태그=<{btn.tag_name}> text='{btn.text.strip()}'")
                    driver.execute_script("arguments[0].click();", btn)
                    return True
            except:
                continue

    print("⚠️ [주의] 하단 예매 버튼을 화면에서 찾지 못했습니다.")
    return False


def scan_and_reserve(driver):
    """
    열차 목록을 스캔하여 빈 좌석을 감지하고, 좌석 클릭 후 하단 [예매] 버튼까지 클릭합니다.
    """
    # 브라우저 Alert 팝업 처리
    try:
        alert = driver.switch_to.alert
        print(f"\n⚠️ [알림창 감지] {alert.text}")
        alert.accept()
        time.sleep(0.5)
    except:
        pass

    if not is_train_list_loaded(driver):
        return False, None

    # sold_out 클래스가 없는 price_box = 빈자리
    available_seats = driver.find_elements(
        By.CSS_SELECTOR,
        "div.price_box:not(.sold_out)"
    )

    if not available_seats:
        return False, None

    # 빈자리 발견 시 처리
    for seat_box in available_seats:
        try:
            seat_text = seat_box.text.replace("\n", " ").strip()
            if not seat_text or seat_text == "-":
                continue

            # 상위 열차 행에서 열차 정보 추출
            try:
                train_row = seat_box.find_element(By.XPATH, "./ancestor::div[contains(@class, 'tck_inner')][1]")
                row_text = train_row.text.replace("\n", " ")
            except:
                row_text = ""

            train_match = re.search(r'KTX[- ]*(\d+)', row_text)
            train_no = train_match.group(0) if train_match else "KTX"

            time_match = re.search(r'(\d{2}:\d{2})\s*~', row_text)
            depart_time = time_match.group(1) if time_match else ""

            # 열차 번호 필터
            if config.TARGET_TRAIN_NUMBERS:
                t_no = train_match.group(1) if train_match else ""
                if t_no not in config.TARGET_TRAIN_NUMBERS:
                    continue

            # 시간대 필터
            if config.TIME_RANGE and depart_time:
                start_t, end_t = config.TIME_RANGE
                if not (start_t <= depart_time <= end_t):
                    continue

            print(f"\n🎯 [빈자리 발견!] {train_no} (출발: {depart_time}) / 좌석 상태: {seat_text}")

            # 1. 좌석 링크 클릭
            seat_link = seat_box.find_elements(By.TAG_NAME, "a")
            if seat_link:
                print("👉 [1단계: 좌석 링크 클릭]")
                driver.execute_script("arguments[0].click();", seat_link[0])
            else:
                print("👉 [1단계: 좌석 박스 클릭]")
                driver.execute_script("arguments[0].click();", seat_box)

            # 2. 하단 [예매] 버튼 클릭 (강화된 클릭 함수 호출)
            print("👉 [2단계: 하단 예매 버튼 찾는 중...]")
            reserve_clicked = click_bottom_reserve_button(driver)

            time.sleep(2)

            # 팝업 처리
            try:
                alert = driver.switch_to.alert
                print(f"ℹ️ [안내 팝업] {alert.text}")
                alert.accept()
            except:
                pass

            return True, f"{train_no} ({depart_time} 출발)"

        except StaleElementReferenceException:
            continue
        except Exception as e:
            continue

    return False, None


def refresh_train_list(driver):
    """
    순수 F5 새로고침 수행
    """
    try:
        driver.refresh()
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(1.5)
    except:
        time.sleep(2)


def check_keyboard_input():
    """
    터미널 논블로킹 키 감지
    """
    if msvcrt and msvcrt.kbhit():
        try:
            char = msvcrt.getch().decode('utf-8', errors='ignore').lower()
            return char
        except:
            return None
    return None


def main():
    print("=" * 65)
    print("      KTX 취소표 실시간 자동 예약 프로그램 (Selenium)")
    print("=" * 65)
    print("📌 [단축키 안내]")
    print("  [ p ] : 모니터링 일시정지 (Pause)")
    print("  [Enter] : 모니터링 다시 시작 (Resume)")
    print("  [ q ] : 프로그램 완전 종료 (Quit)")
    print("=" * 65)

    driver = create_browser()
    target_url = "https://www.korail.com/ticket/search/general"

    try:
        print(f"\n코레일 예매 사이트에 접속합니다... ({target_url})")
        driver.get(target_url)

        print("\n" + "#" * 65)
        print("[사용자 안내]")
        print("1. 크롬 창에서 [로그인]을 완료해주세요.")
        print("2. [출발역, 도착역, 날짜, 시간]을 선택하고 [열차 조회]를 눌러주세요.")
        print("3. 열차 목록이 보이면 (또는 모두 매진 상태라도)")
        print("   이 창에서 [Enter]를 누르면 자동 예매가 시작됩니다!")
        print("")
        print("** '해당 스케줄에 운행하는 열차가 없습니다'가 뜨면")
        print("   F5를 몇 번 눌러 열차 목록이 나온 뒤 Enter를 눌러주세요.")
        print("#" * 65)

        input("\n준비가 완료되었으면 [Enter] 키를 눌러주세요 >>> ")

        retry_count = 0
        no_data_count = 0
        print("\n[모니터링 시작] 취소표 감지 시작... (일시정지: p, 종료: q)\n")

        while retry_count < config.MAX_RETRY_COUNT:
            # 실시간 키 입력 체크 (일시정지/종료)
            key = check_keyboard_input()
            if key == 'p':
                print("\n\n" + "=" * 40)
                print("⏸️ [일시정지됨] 모니터링이 멈췄습니다.")
                print("다시 시작: [Enter] / 종료: q 입력 후 [Enter]")
                print("=" * 40)
                user_cmd = input().strip().lower()
                if user_cmd == 'q':
                    print("🛑 [종료] 사용자에 의해 프로그램이 종료되었습니다.")
                    break
                print("\n▶️ [재개] 모니터링을 다시 시작합니다!\n")
            elif key == 'q':
                print("\n🛑 [종료] 사용자에 의해 모니터링이 종료되었습니다.")
                break

            retry_count += 1
            current_time_str = time.strftime('%H:%M:%S')

            if not is_train_list_loaded(driver):
                no_data_count += 1
                print(f"\r[{current_time_str}] {retry_count}회 | 열차 목록 로딩 대기중... (미로딩 {no_data_count}회)", end="", flush=True)
            else:
                no_data_count = 0
                success, train_info = scan_and_reserve(driver)

                if success:
                    print("\n\n" + "🎉" * 20)
                    print(f"🎉 축하합니다! {train_info} 좌석 선점 성공!")
                    print("👉 지금 바로 [코레일톡 앱] 또는 브라우저에서")
                    print("👉 [예약 승차권 조회/결제]로 들어가 결제를 완료해주세요!")
                    print("⚠️ (주의: 코레일 정책상 약 10~20분 내 미결제 시 자동 취소)")
                    print("🎉" * 20 + "\n")

                    play_alarm()
                    input("\n결제 완료 후 [Enter]를 누르면 프로그램이 종료됩니다.")
                    break

                print(f"\r[{current_time_str}] {retry_count}회 | 전석 매진 - 취소표 대기중... (p:일시정지)", end="", flush=True)

            delay = random.uniform(config.MIN_DELAY_SECONDS, config.MAX_DELAY_SECONDS)
            time.sleep(delay)
            refresh_train_list(driver)

        if retry_count >= config.MAX_RETRY_COUNT:
            print(f"\n[안내] 최대 재시도 횟수({config.MAX_RETRY_COUNT}회) 도달. 모니터링을 종료합니다.")

    except KeyboardInterrupt:
        print("\n\n[종료] Ctrl+C로 안전하게 중단되었습니다.")
    except Exception as e:
        print(f"\n[오류] {e}")
    finally:
        print("\n브라우저를 정리하고 프로그램을 종료합니다.")
        try:
            driver.quit()
        except:
            pass


if __name__ == "__main__":
    main()