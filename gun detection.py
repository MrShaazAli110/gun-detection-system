import cv2
import imutils
import datetime
import os
import sys
import argparse
import time

# Sound alert support on Windows
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

def play_alert_sound():
    if HAS_WINSOUND:
        try:
            # Play a 1500Hz beep for 250ms asynchronously
            winsound.Beep(1500, 250)
        except Exception:
            pass

def main():
    parser = argparse.ArgumentParser(description="Real-time Gun Detection with Snapshot Logging & Alerts")
    parser.add_argument("-c", "--cascade", type=str, default="cascade.xml", help="Path to gun cascade XML file")
    parser.add_argument("-v", "--video", type=str, default=None, help="Path to video file (defaults to webcam)")
    parser.add_argument("-o", "--output", type=str, default="detections", help="Directory to save detected gun snapshots")
    parser.add_argument("--cooldown", type=float, default=2.0, help="Minimum seconds between snapshot recordings")
    parser.add_argument("--no-sound", action="store_true", help="Disable audio alarm beep")
    args = parser.parse_args()

    # Create output directory for detections if it doesn't exist
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)
    print(f"[INFO] Detection snapshots will be saved to: '{output_dir}'")

    # Determine cascade XML path
    cascade_path = args.cascade
    if not os.path.exists(cascade_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cascade_path = os.path.join(script_dir, "cascade.xml")
        
    if not os.path.exists(cascade_path):
        print(f"[ERROR] Cascade file not found at '{args.cascade}' or '{cascade_path}'")
        sys.exit(1)

    # Load Haar cascade
    gun_cascade = cv2.CascadeClassifier(cascade_path)
    if gun_cascade.empty():
        print(f"[ERROR] Failed to load cascade classifier from {cascade_path}")
        sys.exit(1)

    print(f"[INFO] Successfully loaded cascade model from: {cascade_path}")

    # Initialize video capture source (webcam or video file)
    if args.video:
        if not os.path.exists(args.video):
            print(f"[ERROR] Video file not found: {args.video}")
            sys.exit(1)
        camera = cv2.VideoCapture(args.video)
        print(f"[INFO] Opening video file: {args.video}")
    else:
        camera = cv2.VideoCapture(0)
        print("[INFO] Starting webcam stream (Camera 0)...")

    if not camera.isOpened():
        print("[ERROR] Could not open video source.")
        sys.exit(1)

    print("[INFO] Press 'q' or 'ESC' in the feed window to exit.")

    last_snapshot_time = 0
    snapshot_saved_notice_until = 0

    try:
        while True:
            ret, frame = camera.read()
            if not ret or frame is None:
                print("[INFO] Video stream ended or frame unavailable.")
                break

            # Resize frame for faster processing
            frame = imutils.resize(frame, width=650)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Detect guns in grayscale frame
            guns = gun_cascade.detectMultiScale(
                gray,
                scaleFactor=1.3,
                minNeighbors=5,
                minSize=(100, 100)
            )

            gun_count = len(guns)
            current_time = time.time()
            now_dt = datetime.datetime.now()
            timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

            # Draw bounding boxes around detected guns
            for (x, y, w, h) in guns:
                # Draw red bounding box
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                # Draw tag header box
                cv2.rectangle(frame, (x, max(0, y - 25)), (x + w, y), (0, 0, 255), cv2.FILLED)
                cv2.putText(
                    frame, 
                    f"GUN DETECTED ({gun_count})", 
                    (x + 5, y - 7), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, 
                    (255, 255, 255), 
                    2
                )

            # When gun is spotted
            if gun_count > 0:
                # Console Alert Message with timestamp and gun count
                print(f"[ALERT]  {timestamp_str} | THREAT DETECTED: {gun_count} Gun(s) Spotted in feed!")

                # Play Audio Alarm if enabled
                if not args.no_sound:
                    play_alert_sound()

                # Check snapshot cooldown interval
                if (current_time - last_snapshot_time) >= args.cooldown:
                    # Generate filename with date and time
                    date_time_file_str = now_dt.strftime("%Y%m%d_%H%M%S")
                    snapshot_filename = f"gun_alert_{date_time_file_str}_count{gun_count}.jpg"
                    snapshot_path = os.path.join(output_dir, snapshot_filename)

                    # Save image snapshot to file
                    cv2.imwrite(snapshot_path, frame)
                    last_snapshot_time = current_time
                    snapshot_saved_notice_until = current_time + 1.5  # Show notice on UI for 1.5s
                    print(f"[SUCCESS] 📸 Saved detection snapshot: '{snapshot_path}'")

            # UI Overlay Status Banner
            if gun_count > 0:
                status_text = f"[ALERT] {gun_count} GUN(S) SPOTTED!"
                status_color = (0, 0, 255)  # Red
                banner_width = 380
            else:
                status_text = "[NORMAL] System Monitoring"
                status_color = (0, 255, 0)  # Green
                banner_width = 310

            # Top bar status background
            cv2.rectangle(frame, (10, 10), (10 + banner_width, 45), (0, 0, 0), cv2.FILLED)
            cv2.putText(frame, status_text, (20, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)

            # Display Snapshot Saved Notice on Screen
            if current_time < snapshot_saved_notice_until:
                cv2.rectangle(frame, (10, 50), (320, 80), (0, 140, 255), cv2.FILLED)  # Orange tag
                cv2.putText(frame, " Snapshot Saved to File!", (20, 71), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            # Bottom timestamp overlay
            cv2.putText(
                frame, 
                f"TIME: {timestamp_str}", 
                (10, frame.shape[0] - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                (255, 255, 255), 
                1
            )

            # Display feed window
            cv2.imshow("Security Feed - Gun Detection System", frame)

            # Keypress control ('q' or ESC key to quit)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                print("[INFO] Exit signal received.")
                break

    except KeyboardInterrupt:
        print("[INFO] Interrupted by user.")
    finally:
        camera.release()
        cv2.destroyAllWindows()
        print("[INFO] Video feed closed and resources released.")

if __name__ == "__main__":
    main()
