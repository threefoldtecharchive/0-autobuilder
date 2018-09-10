var artifactshost = 'https://bootstrap.grid.tf/kernel/'; // retro-compatible
var artifactshosts = {
    'kernel': 'https://bootstrap.grid.tf/kernel/',
    'flist': 'https://hub.grid.tf/gig-autobuilder/',
    'binary': 'https://download.grid.tf/gig-autobuilder/',
};

var statuscolors = {
    'creating': 'info',
    'error': 'danger',
    'success': 'success',
    'building': 'info',
    'committing': 'info',
    'preparing': 'info',
    'initializing': 'info',
};

var statusmsg = {
    'creating': 'preparing container',
    'error': 'build failed',
    'success': 'build succeeded',
    'building': 'building',
    'committing': 'committing image',
    'preparing': 'preparing the build',
    'initializing': 'initializing the image',
};

var ansiup = new AnsiUp;

var buildio = {};
var buildtime = {};

function progress_update_line(pid, line) {
    var shift = null;

    var append = "";

    // if this line doesn't contains new line
    // append this to last line
    if(line.indexOf("\n") == -1) {
        if(pop = buildio[pid].pop()) {
            if(pop.indexOf("\n") == -1) {
                append = pop;
            }
        }
    }

    append += line;
    buildio[pid].push(ansiup.ansi_to_html(append))

    var running = $('#' + pid + ' pre');
    running.html(buildio[pid].toArray().join(""));
    running.scrollTop(running.prop("scrollHeight"));
}

function progress_update(payload) {
    var pid = payload['id'];
    var line = payload['line'];
    var shift = null;

    if(buildio[pid] == undefined)
        buildio[pid] = new CBuffer(15);

    var lines = line.split(";");
    for(var i in lines)
        progress_update_line(pid, lines[i]);
}

function elapsedtime(now, started) {
    minutes = parseInt((now - started) / 60);
    seconds = ((now - started) % 60).toFixed(0);

    return '<strong>Build time</strong>: ' + minutes + ' minutes ' + seconds + ' seconds ago';
}

function update_times() {
    var items = $('#build-status .panel-body .buildtime');

    // nothing to update
    if(items.length == 0)
        return;

    var now = parseInt(new Date().getTime() / 1000);

    items.each(function(index) {
        var id = $(this).closest('div').attr('id');
        var str = elapsedtime(now, buildtime[id]);
        $(this).html(str);
    });
}

function refresh(data, type) {
    // console.log(data);

    $("#build-" + type).empty();

    if(type == 'status') {
        if(Object.keys(data).length == 0) {
            var text = $('<h2>', {'class': 'text-success'});
            text.append($('<span>', {'class': 'glyphicon glyphicon-ok'}));
            text.append('<br>');
            text.append('Nothing to do right now, all build done.');

            $("#build-" + type).append(text);
            return;
        }
    }

    if(type == 'history') {
        if(Object.keys(data).length == 0) {
            var text = $('<h2>', {'class': 'text-success'});
            text.append($('<span>', {'class': 'glyphicon glyphicon-ok'}));
            text.append('<br>');
            text.append('No history right now.');

            $("#build-" + type).append(text);
            return;
        }
    }

    var zindex = 0;
    for(var idx in data) {
        zindex++;

        var rootcommit = "";

        if(data[idx]['commits'].length > 0) {
            rootcommit = data[idx]['commits'][0]['id'].substr(0, 10);

        } else if(data[idx]['docker'] == 'system') {
            rootcommit = 'internal';

        } else rootcommit = 'docker-' + data[idx]['docker'];

        var root = $('<div>', {'class': 'panel panel-' + statuscolors[data[idx]['status']]});
        var heading = $('<div>', {'class': 'panel-heading'});

        //
        // heading
        //
        var title = data[idx]['name'];
        title = ' <code>[' + rootcommit + ']</code> ' + title;

        if(data[idx]['tag']) {
            title = title + ' [' + data[idx]['tag'] + ']';
        }

        // collapsed heading for history
        if(type == 'history') {
            var id = "panel-" + zindex + "-" + rootcommit
            var collapse = {
                'role': "button",
                'data-toggle': "collapse",
                'href': "#" + id,
                'aria-expanded': "false",
                'aria-controls': id,
            };

            var name = data[idx]['name'];
            if(data[idx]['tag']) {
                name = name + ' [' + data[idx]['tag'] + ']';
            }

            var lnk = $('<a>', collapse).html(name);
            var code = $('<code>').html('[' + rootcommit + ']');

            var title = $('<div>').append(code).append(' ').append(lnk).html();
        }


        var when = new Date(data[idx]['started'] * 1000);

        if(type == 'status')
            buildtime[idx] = data[idx]['started'];

        heading.append($('<h3>', {'class': 'panel-title pull-left'}).html(title));
        heading.append($('<small>', {'class': 'pull-right'}).html(when));
        heading.append($('<div>', {'class': 'clearfix'}));
        root.append(heading);

        //
        // body
        //
        var id = (type == 'history') ? "panel-" + zindex + "-" + rootcommit : idx;
        var clss = (type == 'history') ? "panel-body collapse" : "panel-body";

        var content = $('<div>', {'class': clss, 'id': id});

        var text = $('<p>').html('<strong>Status</strong>: ' + statusmsg[data[idx]['status']]);
        content.append(text);

        var text = $('<p>').html('<strong>Commits</strong>:');
        content.append(text);

        var list = $('<ul>');
        for(var i in data[idx]['commits']) {
            var commit = data[idx]['commits'][i];
            var commitid = commit['id'].substr(0, 10);

            var item = $('<li>').html(
                '<code><a href="' + commit['url'] + '" target="_blank">' + commitid + '</a></code> ' +
                '<code>' + commit['message'] + '</code>' +
                '<small class="pull-right">' + commit['author']['name'] + '</small>'
            );

            list.append(item);
        }

        content.append(list);

        if(data[idx]['status'] == 'error') {
            var text = $('<p>').html('<strong>Error</strong>: ').append('<span>').text(data[idx]['error']);
            content.append(text);
        }

        if(data[idx]['artifact']) {
            var artifact = data[idx]['artifact'];
            var segments = artifact.split("/");

            if(artifactshosts[segments[0]]) {
                var targetlink = artifactshosts[segments[0]] + segments[1];
                var artifactname = segments[1];

            } else {
                // fallback old behavior
                var targetlink = artifactshost + artifact;
                var artifactname = artifact;
            }

            var lnk = $('<a>', {'href': targetlink}).html(artifactname);
            var text = $('<p>').html('<strong>Artifact</strong>: ');
            text.append($('<code>').append(lnk));

            content.append(text);
        }

        if(data[idx]['baseimage']) {
            var baseimg = $('<p>').html('<strong>Base image</strong>: ').append($('<code>').html(data[idx]['baseimage']));
            content.append(baseimg);
        }

        // compute execution time
        var btime = (data[idx]['ended']) ? data[idx]['ended'] : Date.now() / 1000;
        var str = elapsedtime(btime, data[idx]['started']);
        var text = $('<p>', {'class': 'buildtime'}).html(str);
        content.append(text);

        // do not shot console if empty
        var logstr = data[idx]['monitor'] ? data[idx]['monitor'] : "Waiting for logs";
        var logs = $('<pre>').html(ansiup.ansi_to_html(logstr));
        content.append($('<hr>'));
        content.append(logs);

        // probably a build id, not a numeric id
        if(idx.length > 10) {
            data[idx]['id'] = idx;
        }

        if(data[idx]['id']) {
            var options = {
                'href': '/report/' + data[idx]['id'],
                'target': '_blank',
                'style': 'float: right;',
            };

            var report = $('<a>', options).html('View full logs');
            content.append(report);
        }

        root.append(content);

        $("#build-" + type).append(root);
    }
}

function timers() {
    console.log("Set update");
    setInterval(update_times, 1000);
}


function connect() {
    var host = window.location.host;
    socket = new WebSocket("wss://" + host + "/buildio");

    socket.onopen = function() {
        console.log("websocket open");
        $('#disconnected').hide();
    }

    socket.onmessage = function(msg) {
        json = JSON.parse(msg.data);
        // console.log(json);

        switch(json['event']) {
            case "history":
                var length = Object.keys(json['payload']).length;
                // console.log("History update: " + length + ' entries');
                // console.log(json['payload']);
                refresh(json['payload'], "history");
            break;

            case "update":
                // console.log("Build line update");
                // console.log(json['payload']);
                progress_update(json['payload']);
            break;

            case "status":
                // console.log("Build status update");
                // console.log(json['payload']);
                refresh(json['payload'], 'status');
            break;

            default:
                console.log("Unknown type");
                console.log(json);
        }
    }

    socket.onclose = function() {
        $('#disconnected').show();
        setTimeout(connect, 2000);
    }
}

$(document).ready(function() {
    connect();
    timers();
});

