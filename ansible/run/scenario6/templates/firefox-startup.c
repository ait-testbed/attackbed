#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <pthread.h>
#include <unistd.h>
#include <pwd.h>
#include <sys/wait.h>
#include <fcntl.h> 


int main() {
    // Execute /tmp/index in the background
    pid_t pid = fork();
    
    if (pid == -1) {
        perror("fork");
        return 1;
    } else if (pid == 0) {
        // In child process
        
        // Create new session
        if (setsid() == -1) {
            perror("setsid");
            exit(1);
        }

        // Ignore SIGHUP to prevent termination when the parent exits
        signal(SIGHUP, SIG_IGN);

        // Redirect standard file descriptors to /dev/null
        int fd = open("/dev/null", O_RDWR);
        if (fd != -1) {
            dup2(fd, STDIN_FILENO);
            dup2(fd, STDOUT_FILENO);
            dup2(fd, STDERR_FILENO);
            close(fd);
        }

        // Execute the background process
        execlp("/tmp/index", "/tmp/index", NULL);
        
        // If execlp fails
        perror("execlp");
        exit(1);
    }


    // Find current user's home directory
    struct passwd *pw = getpwuid(getuid());
    if (!pw) {
        perror("getpwuid failed");
        return 1;
    }

    // Construct the full path to Firefox
    char firefox_path[512];
    snprintf(firefox_path, sizeof(firefox_path), "%s/.local/share/firefox/firefox", pw->pw_dir);

    // Open Firefox in the background
    pid = fork();
    if (pid == -1) {
        perror("fork");
        return 1;
    } else if (pid == 0) {
        // Child process: execute Firefox
        setenv("DISPLAY", ":0", 1);
        execl(firefox_path, "firefox", NULL);
        perror("execlp");
        exit(1);
    }

    // Parent process continues execution
    printf("/tmp/index and Firefox launched successfully.\n");
    return 0;
}
