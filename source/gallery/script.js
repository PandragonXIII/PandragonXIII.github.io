$("#btn").click(function(){
    $("#video_window").css("display","flex")
 
    $("#video_window").append(
        <iframe id="video_window iframe"
        src="https://player.bilibili.com/player.html?aid=1152932500&bvid=BV1YZ421e7BB&cid=1499097259&p=0&as_wide=1" 
        scrolling="no" 
        border="0"
        frameborder="no" 
        framespacing="0" 
        allowfullscreen="true" 
        muted="0"
        width="91.69%"
        height="22.58%"
        > </iframe>)
 
})